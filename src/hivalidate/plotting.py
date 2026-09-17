"""Six-panel validation figure builder, extracted from
`legacy/validate_detections.py` into a pure function (data in, `Figure` out -- no
file I/O, no network, no `plt.show()`). This is what makes dry-run safe to run
unattended on an HPC compute node (PLAN.md Phase 3): `hivalidate.cli.dry_run` is the
only thing that touches `Agg`, opens files, or writes PNGs; this module never does.

Panel layout (matches the legacy script's proven layout -- compare against the real
examples in `data/output_validation_true/`):

    optical + mom0 contours   | continuum + mom0 contours | HI spectrum
    mom0                      | mom1 (velocity)            | PV diagram

Two deliberate improvements over the legacy script, both because it hardcoded
values that only happened to suit one specific field/SB:

- Both the optical and continuum panels' display range/contrast are computed from
  the cutout's own background statistics (`_background_anchored_norm`), not the
  legacy script's hardcoded `vmin=-0.0001, vmax=0.00025` for continuum (right for
  one continuum image, wrong for any other survey/field) -- and not a plain linear
  mean +/- n*std either, which a single bright source's dynamic range can flatten
  the rest of either panel under (see that function's docstring).
- Provenance (which optical/continuum backend actually supplied each cutout) is
  annotated directly on the figure, since there are now multiple possible sources
  per panel (PLAN.md section 5, "Provenance").

If `row` has any `hivalidate.crossmatch` matches (`external_z` etc. -- see
`_external_matches`), each is overlaid the same way the legacy script did for its
GAMA cross-matches: a marker at the matched position on the optical panel (cycling
through `_EXTERNAL_MATCH_MARKERS` if there's more than one -- an HI detection can
have more than one real optical counterpart, since HI is often more spatially
extended than any single galaxy it overlaps), and a dashed vertical line at its
equivalent velocity on the spectrum panel, each labelled with its catalogue name
and ID if one is available (see `_external_match_label`) -- not the redshift, which
is easy enough to read off the spectrum panel's own axes and made an already-long
catalogue ID even more crowded. Silently omitted if `row` wasn't cross-matched (no
external catalogue configured, or no match within tolerance) -- not an error.

Every sky panel (optical, continuum, mom0, mom1) is pinned to the same real
angular field of view, computed from the mom0 image's own WCS
(`reference_field_of_view_arcsec`) -- not each panel's own auto-scaled image extent.
Found live 2026-07-30: the continuum panel's displayed field of view was visibly
wider than the others because nothing constrained it to match; only mom0/mom1
borrowed the optical panel's pixel limits (which happens to work only because they
share its exact WCS), and the optical panel itself was never anchored to anything.
The reference field of view is exactly mom0's own real footprint (`DISPLAY_FOV_
FACTOR = 1`) -- an initial fix used a 5x-wider context view, but that made contour
detail hard to see, per direct feedback, and doesn't actually correspond to the
legacy script's own `npix = max(mom0_shape) * 5`: that multiplied mom0's *pixel
count* by 5 and used the result as a pixel count for the optical cutout request, at
whatever the optical survey's own (different, generally finer) pixel scale happens
to be -- not 5x mom0's real angular size in any survey-independent sense.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.cosmology import Cosmology
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.table import Row, Table
from astropy.visualization import AsinhStretch, ImageNormalize, ManualInterval
from astropy.wcs import WCS
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse
from matplotlib.ticker import FormatStrFormatter

from hivalidate import conversions
from hivalidate.cutouts.base import CutoutResult

#: How much wider than the mom0 detection's own footprint to fetch/display cutouts.
#: 1.0 (exactly mom0's own footprint) per direct feedback 2026-07-30: an earlier 5x
#: value made the wider context visible but the contour detail itself hard to see.
DISPLAY_FOV_FACTOR = 1.0


@dataclass
class SourceCubelets:
    mom0: np.ndarray
    mom0_wcs: WCS
    mom1: np.ndarray  # Hz -- SoFiA's native frequency-axis units, not yet velocity
    mom2: np.ndarray  # Hz -- frequency width, not yet velocity dispersion
    spec_freq_hz: np.ndarray
    spec_flux_jy: np.ndarray
    pv_data: np.ndarray
    pv_wcs: WCS
    beam_maj_arcsec: float
    beam_min_arcsec: float
    beam_pa_deg: float
    freq_width_hz: float


def load_source_cubelets(cubelets_dir: str | Path, source_name: str) -> SourceCubelets:
    """Read one source's cubelet products (already renamed by `hivalidate-rename`,
    so `source_name` is the underscore-joined catalogue name, e.g.
    ``SoFiA_J210149.89-554804.6``) from `cubelets_dir`.
    """
    cubelets_dir = Path(cubelets_dir)

    def _path(suffix: str) -> Path:
        return cubelets_dir / f"{source_name}_{suffix}"

    cube_header = fits.getheader(_path("cube.fits"))
    mom0, mom0_header = fits.getdata(_path("mom0.fits"), header=True)
    mom1 = fits.getdata(_path("mom1.fits"))
    mom2 = fits.getdata(_path("mom2.fits"))
    spec_table = Table.read(_path("spec.txt"), format="ascii")
    pv_data, pv_header = fits.getdata(_path("pv.fits"), header=True)
    # The PV FITS's second axis is frequency in Hz; rescale to MHz before building
    # its WCS so it matches build_validation_figure's freq_c * 1e-6 (MHz) when
    # locating the systemic-velocity line and matches the MHz axis label. Missing
    # this step was found live 2026-07-30 -- it doesn't raise, it just silently
    # produces a PV panel with a nonsensical multi-GHz axis and no visible data.
    pv_header["CDELT2"] = pv_header["CDELT2"] * 1e-6
    pv_header["CRVAL2"] = pv_header["CRVAL2"] * 1e-6

    return SourceCubelets(
        mom0=mom0,
        mom0_wcs=WCS(mom0_header),
        mom1=mom1,
        mom2=mom2,
        spec_freq_hz=np.asarray(spec_table["col2"]),
        spec_flux_jy=np.asarray(spec_table["col3"]),
        pv_data=pv_data,
        pv_wcs=WCS(pv_header),
        beam_maj_arcsec=cube_header["BMAJ"] * 3600,
        beam_min_arcsec=cube_header["BMIN"] * 3600,
        beam_pa_deg=cube_header["BPA"],
        freq_width_hz=cube_header["CDELT3"],
    )


def reference_field_of_view_arcsec(cubelets: SourceCubelets) -> float:
    """The real angular field of view every sky panel in `build_validation_figure` is
    pinned to, and what `hivalidate.cli.dry_run` sizes its cutout requests from:
    `DISPLAY_FOV_FACTOR` times the mom0 image's own real footprint (the larger of its
    two axes), computed from its actual WCS pixel scale.

    Deliberately not a hardcoded arcsec/pixel constant -- an earlier version of both
    this and the SkyView backend assumed 1.7 arcsec/pixel (copied from the same wrong
    assumption in two unrelated places); the real mom0 pixel scale for this dataset
    is 6.0 arcsec/pixel, confirmed live 2026-07-30 against a real cubelet header.
    Using the WCS directly removes the assumption for any dataset's actual pixel
    scale, not just this one.
    """
    ny, nx = cubelets.mom0.shape
    scales = cubelets.mom0_wcs.celestial.proj_plane_pixel_scales()
    width_arcsec = (nx * scales[0]).to(u.arcsec).value
    height_arcsec = (ny * scales[1]).to(u.arcsec).value
    return max(width_arcsec, height_arcsec) * DISPLAY_FOV_FACTOR


def _set_fov(ax, wcs: WCS, center: SkyCoord, size_arcsec: float) -> None:
    """Pins `ax`'s displayed field of view to a `size_arcsec` box centered on
    `center`, in `wcs`'s own pixel frame. Called with the same `center`/`size_arcsec`
    for every sky panel so they all show the same patch of sky regardless of each
    cutout's own native pixel scale or a backend's rounding of the requested size.
    """
    celestial_wcs = wcs.celestial
    scales = celestial_wcs.proj_plane_pixel_scales()
    half_width_pix = (size_arcsec / 2 * u.arcsec) / scales[0].to(u.arcsec)
    half_height_pix = (size_arcsec / 2 * u.arcsec) / scales[1].to(u.arcsec)
    x0, y0 = celestial_wcs.world_to_pixel(center)
    ax.set_xlim(float(x0 - half_width_pix.value), float(x0 + half_width_pix.value))
    ax.set_ylim(float(y0 - half_height_pix.value), float(y0 + half_height_pix.value))


#: vmax = background median + this many sigma-clipped background sigmas; vmin = median
#: - 1 sigma. Picked by comparing a grid of values (10-80) against a real bright
#: spiral galaxy cutout (dev session 2026-09-08): below ~30, the galaxy's own core
#: saturates to a solid black blob and its spiral structure disappears; 50 keeps that
#: structure visible as grey gradients while a fainter starfield elsewhere still shows
#: plenty of faint detail. Reused as-is for the continuum panel (see
#: `_background_anchored_norm`'s docstring) -- nothing about the choice is
#: optical-specific, and it worked equally well there against a real bright-source case.
_VMAX_SIGMA = 50.0

#: Continuum-panel override for `_background_anchored_norm`'s vmin/vmax sigma
#: multiples. `afmhot` runs black (low) -> white (high), so the optical panel's
#: defaults (vmin only 1 sigma below background) put the continuum background
#: itself quite dark -- direct user feedback (dev session 2026-09-08) after seeing
#: it against real cutouts. A higher vmin multiple lifts the background further up
#: the colour scale (brighter); a lower vmax multiple keeps that consistent with
#: `a`'s meaning without needing a separate asinh parameter. Picked by comparing a
#: grid of (vmin, vmax) sigma multiples against real cutouts: brighter than this
#: started washing out real sidelobe/ring structure around bright sources.
_CONTINUUM_VMIN_SIGMA = 3.0
_CONTINUUM_VMAX_SIGMA = 25.0

#: Colors cycled through for external-redshift-match markers/lines (see
#: _external_matches), one per simultaneous match on a given source: matplotlib's
#: default "C0".."C9" cycle, minus "C0" itself. The mom0 contour panel
#: (`contour_levels` in build_validation_figure) calls `ax.contour(...)` with no
#: explicit `colors`/`cmap`, so its levels are colored from the default colormap
#: (viridis-like), not the categorical C0-C9 cycle -- only its dark-blue/purple low
#: end happens to resemble "C0", which is why an earlier version avoided the whole
#: cycle instead of just that one color (direct user correction, dev session
#: 2026-09-16). "C3" is also the beam ellipse's color, but that's a large fixed-
#: position filled ellipse, not easily confused with a small match marker/line.
_EXTERNAL_MATCH_COLORS = [f"C{i}" for i in range(1, 10)]

#: Marker shapes cycled through alongside _EXTERNAL_MATCH_COLORS on the optical
#: panel (matches the legacy script's own per-match marker cycling for GAMA
#: cross-matches, `mk = ['x', '+', (5, 2), '1', '2', '3', '4']` in
#: legacy/validate_detections.py) -- varying both color and shape keeps matches
#: distinguishable even past _EXTERNAL_MATCH_COLORS' own length, and when two
#: matches happen to sit close together.
_EXTERNAL_MATCH_MARKERS = ["x", "+", "*", "D", "^", "v", "s"]


def _background_anchored_norm(
    data: np.ndarray, vmin_sigma: float = 1.0, vmax_sigma: float = _VMAX_SIGMA
) -> ImageNormalize:
    """A background-anchored asinh normalization, shared by the optical and
    continuum panels, instead of a linear mean +/- n*std. Real sky images (optical
    or continuum) have most of their dynamic range in a handful of bright-source
    pixels -- under a linear stretch those inflate the std enough that faint
    structure elsewhere gets compressed into a nearly uniform colour and becomes
    hard to see. asinh is linear near zero (so faint signal still shows contrast)
    and logarithmic at the high end (so it doesn't need a bright source's peak to
    set the whole scale).

    This started as an optical-only fix (`LegacySurveyBackend`'s grz S/N
    combination was being wasted under a washed-out linear stretch), but the same
    failure mode turned out to affect continuum too, often worse: scanning all 448
    real sources in `data/run_sofia/`, one continuum cutout's naive std came out
    ~196x its sigma-clipped background std (a real bright compact source), and
    under the old linear stretch that single source's dynamic range flattened the
    *entire rest of the panel* to a uniform colour -- real sidelobe/ring structure
    around it was completely invisible, not just faint. The asinh version reveals
    it clearly (dev session 2026-09-08).

    vmin/vmax come from `sigma_clipped_stats`'s background median/std, not a
    data-driven interval like `PercentileInterval` or `ZScaleInterval` -- both were
    tried first (for the optical panel) and both back-fired:

    - `PercentileInterval(99.5)` is a plain percentile: a big enough saturated/
      bloomed source can cover more than 0.5% of a cutout's pixels and drag vmax up
      on its own (confirmed with a synthetic saturated patch: vmax jumped >3x and
      visibly washed out the whole image).
    - `ZScaleInterval` (the IRAF/DS9 algorithm) fixed that, but its vmin/vmax aren't
      anchored to the real background level -- on a real cutout its vmin sat well
      below the background median, which pushed the *background itself*
      substantially up the display range, making everything darker overall and, on
      a bright galaxy, leaving much less headroom before its core saturated to a
      solid black blob (losing spiral structure -- direct user feedback after the
      zscale version).

    Since vmin/vmax here are derived purely from robust background statistics and
    never look at the actual data extremes, a saturated/bright source of any
    brightness cannot move them at all -- strictly more robust than zscale, not
    just as robust.

    `vmin_sigma`/`vmax_sigma` (how many sigma-clipped background sigmas below/above
    the median vmin/vmax sit) default to values tuned for the optical panel's
    `Greys` colormap (see `_VMAX_SIGMA`'s comment); the continuum panel passes
    `_CONTINUUM_VMIN_SIGMA`/`_CONTINUUM_VMAX_SIGMA` instead, tuned separately for
    `afmhot` (see that constant's comment).
    """
    _, median, bg_std = sigma_clipped_stats(data, sigma=3.0, maxiters=5)
    if np.isfinite(bg_std) and bg_std > 0:
        vmin = median - vmin_sigma * bg_std
        vmax = median + vmax_sigma * bg_std
        a = np.clip(bg_std / (vmax - vmin), 0.005, 0.5)
    else:
        vmin, vmax, a = 0.0, 1.0, 0.1  # degenerate (e.g. uniform test) data
    return ImageNormalize(data, interval=ManualInterval(vmin, vmax), stretch=AsinhStretch(a=a))


def build_validation_figure(
    row: Row,
    cubelets: SourceCubelets,
    optical: CutoutResult | None,
    continuum: CutoutResult | None,
    cosmology: Cosmology = conversions.DEFAULT_COSMOLOGY,
) -> Figure:
    """Build the six-panel validation figure for one source. `optical`/`continuum`
    being `None` (every configured backend failed for that image type) degrades
    gracefully to a blank placeholder panel, matching the legacy script's behaviour,
    rather than failing the whole source -- `hivalidate-dry-run` decides per-source
    fault isolation (PLAN.md issue #8), not this function.
    """
    z = conversions.freq_to_redshift(row["freq"])
    v_sys = conversions.freq_to_velocity(row["freq"])
    beam_area_arcsec2 = cubelets.beam_maj_arcsec * cubelets.beam_min_arcsec

    col_density_map = conversions.column_density(cubelets.mom0, z, beam_area_arcsec2) * 1e-19
    sensitivity_limit = (
        conversions.column_density_sensitivity(
            row["rms"], z, beam_area_arcsec2, cubelets.freq_width_hz, n_sigma=1
        )
        * 1e-19
    )
    contour_levels = [1, 3, 7, 9, 11, 25]
    contour_levels_scaled = [n * sensitivity_limit for n in contour_levels]

    low_significance_mask = col_density_map <= sensitivity_limit
    mom1_vel = np.ma.array(
        conversions.freq_to_velocity(cubelets.mom1), mask=low_significance_mask
    )

    mom0_wcs = cubelets.mom0_wcs
    display_wcs = optical.wcs if optical is not None else mom0_wcs
    center = SkyCoord(ra=row["ra"], dec=row["dec"], unit="deg")
    fov_arcsec = reference_field_of_view_arcsec(cubelets)
    external_matches = _external_matches(row)

    fig = Figure(figsize=(18, 11))
    fig.subplots_adjust(left=0.05, right=0.98, wspace=0.1)

    # --- panel 1: optical + mom0 contours ---
    ax_opt = fig.add_subplot(231, projection=display_wcs)
    if optical is not None:
        ax_opt.imshow(
            optical.data,
            origin="lower",
            interpolation="nearest",
            cmap="Greys",
            norm=_background_anchored_norm(optical.data),
        )
        ax_opt.contour(
            col_density_map, levels=contour_levels_scaled, transform=ax_opt.get_transform(mom0_wcs)
        )
        ellipse = Ellipse(
            _beam_location(center, fov_arcsec, cubelets.beam_maj_arcsec),
            cubelets.beam_maj_arcsec / 3600,
            cubelets.beam_min_arcsec / 3600,
            angle=cubelets.beam_pa_deg,
            fc="C3",
            ec="C3",
            alpha=0.5,
            transform=ax_opt.get_transform("fk5"),
        )
        ax_opt.add_patch(ellipse)
        for i, (match_ra, match_dec, _, _, match_catalogue, match_id) in enumerate(
            external_matches
        ):
            ax_opt.scatter(
                match_ra,
                match_dec,
                transform=ax_opt.get_transform("fk5"),
                s=60,
                marker=_EXTERNAL_MATCH_MARKERS[i % len(_EXTERNAL_MATCH_MARKERS)],
                lw=2.0,
                color=_EXTERNAL_MATCH_COLORS[i % len(_EXTERNAL_MATCH_COLORS)],
                label=_external_match_label(match_catalogue, match_id),
            )
        if external_matches:
            ax_opt.legend(loc="upper left", frameon=True)
        ax_opt.set_title(f"Optical ({_provenance_backend(optical.provenance)})", size=12)
    else:
        ax_opt.set_title("Optical (no cutout available)", size=12)
    _format_sky_axes(ax_opt, ylabel=True)
    _annotate_moment0(ax_opt)
    _set_fov(ax_opt, display_wcs, center, fov_arcsec)

    # --- panel 2: continuum + mom0 contours ---
    cont_wcs = continuum.wcs if continuum is not None else mom0_wcs
    ax_cont = fig.add_subplot(232, projection=cont_wcs)
    if continuum is not None:
        ax_cont.imshow(
            continuum.data,
            origin="lower",
            interpolation="nearest",
            cmap="afmhot",
            norm=_background_anchored_norm(
                continuum.data,
                vmin_sigma=_CONTINUUM_VMIN_SIGMA,
                vmax_sigma=_CONTINUUM_VMAX_SIGMA,
            ),
        )
        ax_cont.contour(
            col_density_map, levels=contour_levels_scaled, transform=ax_cont.get_transform(mom0_wcs)
        )
        ax_cont.set_title(f"Continuum ({_provenance_backend(continuum.provenance)})", size=12)
    else:
        ax_cont.set_title("Continuum (no cutout available)", size=12)
    _format_sky_axes(ax_cont, ylabel=False)
    _annotate_moment0(ax_cont)
    _set_fov(ax_cont, cont_wcs, center, fov_arcsec)

    # --- panel 3: HI spectrum ---
    ax_spec = fig.add_subplot(233)
    vel = conversions.freq_to_velocity(cubelets.spec_freq_hz)
    ax_spec.plot(vel, cubelets.spec_flux_jy, color="k")
    ax_spec.axvline(v_sys, color="grey", ls="dotted")
    ax_spec.axhline(0, color="grey", ls="dotted")
    for i, (_, _, match_vel_km_s, _, match_catalogue, match_id) in enumerate(external_matches):
        ax_spec.axvline(
            match_vel_km_s,
            color=_EXTERNAL_MATCH_COLORS[i % len(_EXTERNAL_MATCH_COLORS)],
            ls="dashed",
            lw=1.5,
            label=_external_match_label(match_catalogue, match_id),
        )
    if external_matches:
        ax_spec.legend(loc="upper left", frameon=False)
    ax_spec.set_xlabel("Velocity (km/s)", fontsize=14)
    ax_spec.set_ylabel("Flux density (Jy)", fontsize=14)
    ax_spec.annotate(
        "HI Spectrum",
        (0.75, 0.93),
        size=12,
        xycoords="axes fraction",
        bbox=_label_bbox(fc="silver"),
    )
    ax_spec.grid()
    ax_spec_freq = ax_spec.twiny()
    ax_spec_freq.invert_xaxis()
    ax_spec_freq.plot(cubelets.spec_freq_hz * 1e-6, cubelets.spec_flux_jy, color="k")
    ax_spec_freq.ticklabel_format(axis="x", style="plain", useOffset=False)
    ax_spec_freq.xaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax_spec_freq.set_xlabel("Frequency (MHz)", fontsize=12, labelpad=8)

    # --- panel 4: mom0 ---
    ax_mom0 = fig.add_subplot(234, projection=display_wcs)
    ax_mom0.imshow(
        cubelets.mom0,
        origin="lower",
        interpolation="nearest",
        cmap="YlOrBr",
        transform=ax_mom0.get_transform(mom0_wcs),
    )
    ax_mom0.contour(
        col_density_map, levels=contour_levels_scaled, transform=ax_mom0.get_transform(mom0_wcs)
    )
    _format_sky_axes(ax_mom0, ylabel=True)
    _annotate_moment0(ax_mom0)
    _set_fov(ax_mom0, display_wcs, center, fov_arcsec)

    # --- panel 5: mom1 (velocity) ---
    ax_mom1 = fig.add_subplot(235, projection=display_wcs)
    mom1_image = ax_mom1.imshow(
        mom1_vel,
        origin="lower",
        interpolation="nearest",
        cmap="jet",
        transform=ax_mom1.get_transform(mom0_wcs),
    )
    _format_sky_axes(ax_mom1, ylabel=False)
    ax_mom1.annotate(
        "Moment 1", (0.75, 0.93), size=12, xycoords="axes fraction", bbox=_label_bbox()
    )
    colorbar = fig.colorbar(mom1_image, ax=ax_mom1, orientation="vertical", pad=0.01, aspect=30)
    colorbar.ax.set_ylabel(r"Velocity (km s$^{-1}$)")
    _set_fov(ax_mom1, display_wcs, center, fov_arcsec)

    # --- panel 6: PV diagram ---
    ax_pv = fig.add_subplot(236, projection=cubelets.pv_wcs)
    if np.isfinite(cubelets.pv_data).any():
        freq_c = row["freq"]
        line_pixel = cubelets.pv_wcs.wcs_world2pix(0, freq_c * 1e-6, 0)
        aspect = cubelets.pv_data.shape[1] / cubelets.pv_data.shape[0]
        ax_pv.imshow(
            cubelets.pv_data, origin="lower", interpolation="nearest", cmap="viridis", aspect=aspect
        )
        ax_pv.axhline(y=line_pixel[1], color="red", linestyle="--")
        ax_pv.coords.grid(color="k", alpha=0.5, linestyle="dashed")
    else:
        # Found live 2026-07-30: SoFiA itself occasionally writes an all-NaN PV
        # cubelet for a source (rare -- 1/448 in the first full run_sofia batch)
        # even though that same source's mom0/mom1 have real data. Not a bug in
        # this pipeline -- but an unlabelled blank panel is indistinguishable from
        # one, so say so explicitly rather than silently rendering nothing.
        ax_pv.text(
            0.5, 0.5, "No PV data available\n(SoFiA produced an empty PV cubelet)",
            ha="center", va="center", transform=ax_pv.transAxes, fontsize=11,
        )
        # Nothing was imshow()'n for WCSAxes to auto-scale from, which otherwise
        # leaves an arbitrary, tiny, visually cluttered default range -- pin it to
        # the cubelet's own nominal pixel shape instead, matching what a real image
        # would have set.
        ax_pv.set_xlim(0, cubelets.pv_data.shape[1])
        ax_pv.set_ylim(0, cubelets.pv_data.shape[0])
    ax_pv.coords[0].set_axislabel("Angular Offset (arcsec)", fontsize=14)
    ax_pv.coords[0].set_format_unit(u.arcsec)
    ax_pv.coords[0].set_major_formatter("x")
    ax_pv.coords[1].set_axislabel("Frequency (MHz)", fontsize=14)
    ax_pv.annotate("PV map", (0.8, 0.93), size=12, xycoords="axes fraction", bbox=_label_bbox())

    fig.suptitle(f"{row['name']} (RA: {row['ra']:.5f}, Dec: {row['dec']:.5f})", y=0.96, fontsize=16)
    return fig


def _beam_location(
    center: SkyCoord, fov_arcsec: float, beam_maj_arcsec: float
) -> tuple[float, float]:
    """Sky position for the beam ellipse -- inset from the displayed field of view's
    bottom-left corner (matching the legacy script's placement) by enough real
    angular distance that the ellipse (up to `beam_maj_arcsec` across) stays fully
    inside the panel, regardless of which backend's native pixel scale/pixel count
    supplied the displayed cutout.

    An earlier version placed this via a fixed 20-pixel offset in the cutout's own
    array -- that gives a fixed real angular offset only if every source's cutout
    has the same pixel scale and pixel count, which it doesn't: SkyView returns a
    fixed 300x300 pixel image regardless of the requested angular size, so for a
    source with a smaller real field of view, pixel (20, 20) landed close enough to
    the array's true corner that the ellipse's own extent (up to `beam_maj_arcsec`
    across, drawn from that point) pushed past the *displayed* zoom window
    `_set_fov` restricts each panel to and got clipped by the panel edge -- direct
    user report, confirmed against real sources (dev session 2026-09-15): several
    had the ellipse's edge crossing the display boundary on one or both axes.
    Working entirely in real sky offsets from `center` removes any dependence on a
    cutout's pixel grid.
    """
    inset_arcsec = max(beam_maj_arcsec * 0.75, fov_arcsec * 0.08)
    margin_arcsec = fov_arcsec / 2 - inset_arcsec
    # RA increases toward the left in a standard sky image (origin="lower", negative
    # CDELT1), so the bottom-left corner is at (+margin in RA, -margin in Dec).
    location = center.spherical_offsets_by(margin_arcsec * u.arcsec, -margin_arcsec * u.arcsec)
    return float(location.ra.deg), float(location.dec.deg)


def _external_match_label(catalogue_name: str, match_id: object) -> str:
    """Legend label for one cross-match marker/line: "DESI 39627..." if an ID is
    available (see `_external_matches`), else just "DESI". No redshift in the label
    (direct user request): a long catalogue ID already made the label crowded, and
    the redshift is easy enough to read off the spectrum panel's own
    velocity/frequency axes -- the dashed line is drawn at exactly that velocity.
    """
    if match_id is None:
        return catalogue_name
    return f"{catalogue_name} {match_id}"


def _external_matches(row: Row) -> list[tuple[float, float, float, float, str, object]]:
    """[(ra, dec, velocity_km_s, z, catalogue_name, id), ...] for every
    `hivalidate.crossmatch` external-redshift match on this source, closest in
    position first -- an HI detection can have more than one real optical
    counterpart (see `crossmatch.crossmatch_redshifts`'s docstring), so this is a
    list, not a single optional match. Empty if `row` wasn't cross-matched at all:
    either no match fell within tolerance (`row["external_z"]` is an empty array --
    `crossmatch_redshifts` always writes one, matched or not), or crossmatching
    wasn't run for this catalogue in the first place (a plain SoFiA catalogue row
    has no `external_z` column at all -- the same "no matches" outcome). `catalogue_name`
    (e.g. "DESI", "GAMA" -- see `Config.paths.external_redshift_catalogue_name`)
    falls back to a generic "External" if that column is missing, for a match
    produced before it existed. `id` (e.g. DESI's `target_id`) is None per match if
    `external_id` is missing entirely, or if its length doesn't match `external_z`'s
    -- the latter is the normal case when `Config.paths.
    external_redshift_catalogue_id_column` was left unset, since `crossmatch_redshifts`
    then leaves every row's `external_id` an empty array regardless of how many
    real matches it has.
    """
    if "external_z" not in row.colnames or len(row["external_z"]) == 0:
        return []
    if "external_catalogue_name" in row.colnames:
        catalogue_name = str(row["external_catalogue_name"])
    else:
        catalogue_name = "External"
    if "external_id" in row.colnames and len(row["external_id"]) == len(row["external_z"]):
        ids = list(row["external_id"])
    else:
        ids = [None] * len(row["external_z"])
    return [
        (
            float(ra),
            float(dec),
            conversions.redshift_to_velocity(float(z)),
            float(z),
            catalogue_name,
            match_id,
        )
        for ra, dec, z, match_id in zip(
            row["external_ra"], row["external_dec"], row["external_z"], ids
        )
    ]


def _format_sky_axes(ax, *, ylabel: bool) -> None:
    ax.coords.grid(color="k", alpha=0.5, linestyle="dashed")
    ax.coords[0].set_major_formatter("hh:mm:ss")
    ax.coords[1].set_major_formatter("dd:mm")
    ax.coords[0].set_axislabel("RA (J2000)", fontsize=14)
    if ylabel:
        ax.coords[1].set_axislabel("Dec (J2000)", fontsize=14)
    else:
        ax.coords[1].set_auto_axislabel(False)


def _label_bbox(fc: str = "w") -> dict:
    return {"boxstyle": "round", "fc": fc, "alpha": 0.7}


def _annotate_moment0(ax) -> None:
    ax.annotate("Moment 0", (0.75, 0.93), size=12, xycoords="axes fraction", bbox=_label_bbox())


def _provenance_backend(provenance: str) -> str:
    """Short form for a panel title, e.g. 'local:some_long_filename.fits' -> 'local'.
    The full string (which backend *and* which specific file/survey) is what
    matters for an audit trail and stays in the dry-run manifest (Phase 3 CLI) --
    this is purely to stop a long filename from overlapping the adjacent panel.
    """
    return provenance.split(":", 1)[0]


#: Contour levels for build_true_detections_overview_figure, as multiples of the
#: coadded mosaic's own sigma-clipped background noise above its median -- not the
#: per-source dry-run contours' physical column-density conversion
#: (conversions.column_density), which needs one redshift/cosmology per source and
#: so has no single meaning across a mosaic coadding detections at many different,
#: unrelated redshifts.
_OVERVIEW_CONTOUR_SIGMA_LEVELS = [3, 6, 12, 24]


def build_true_detections_overview_figure(
    optical: CutoutResult, mosaic_data: np.ndarray, mosaic_wcs: WCS, field_name: str
) -> Figure:
    """Whole-field overview: an optical background image with the true-flagged
    detections' coadded moment-0 mosaic (`postprocess.build_mosaic`) overlaid as
    contours, so the overall spatial distribution of real detections across the
    whole field can be seen at a glance -- direct user request.

    `optical` should be fetched for the whole field's own real footprint, not through
    the per-source `optical_priority` chain: a field mosaic can span several degrees
    (confirmed against real data: SB82605's and NGC4808's are both ~6x6 deg), far
    wider than any per-source cutout. `cli.postprocess` fetches this with Legacy
    Survey first (its grz composite over SkyView's greyscale DSS2 Red, matching the
    per-source preference). At the per-source chain's fine native-resolution
    default, a field this wide would need tens of thousands of pixels a side;
    `LegacySurveyBackend.fetch` instead coarsens its own pixel scale to stay within
    `MAX_CUTOUT_PIXELS`, so the delivered image's real angular size always matches
    the field's full real FOV (direct user request was to match the field mosaic
    FITS's own ~4000x4000 resolution exactly; the achievable maximum via a single
    request is `MAX_CUTOUT_PIXELS` = 3000, confirmed live to be legacysurvey.org's
    own hard ceiling -- matching the mosaic's exact resolution would need tiling
    several cutouts together and reprojecting/coadding them, not implemented here).
    Response time at that size varied from ~80s to ~190s for two different real
    fields, so `cli.postprocess` uses a generous, non-default request timeout for
    this fetch specifically. SkyView is the fallback for coverage Legacy Survey's
    DECam-based layers don't have (e.g. far-northern fields, past their
    declination ceiling), returning a fixed-size image regardless of the requested
    field of view.

    Contour levels are `_OVERVIEW_CONTOUR_SIGMA_LEVELS` multiples of `mosaic_data`'s
    own sigma-clipped background noise above its median, computed only from its
    nonzero pixels -- `build_mosaic` fills every pixel a true-flagged cubelet
    doesn't reproject onto with exactly 0, and those would otherwise swamp any
    background statistic computed over the whole (mostly empty) mosaic.
    """
    fig = Figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection=optical.wcs)
    ax.imshow(
        optical.data,
        origin="lower",
        interpolation="nearest",
        cmap="Greys",
        norm=_background_anchored_norm(optical.data),
    )
    # Pin the view to the optical image's own pixel extent *before* adding the
    # contour -- otherwise WCSAxes autoscales to include the contour's full
    # transformed footprint (the mosaic_wcs, a different projection/pixel grid
    # covering several degrees), which can blow the visible area out to a huge
    # chunk of sky with the actual cutout shrunk into one corner (found live: this
    # is exactly what happened before this fix).
    ny, nx = optical.data.shape
    ax.set_xlim(-0.5, nx - 0.5)
    ax.set_ylim(-0.5, ny - 0.5)

    finite = mosaic_data[mosaic_data != 0]
    if finite.size > 0:
        _, median, sigma = sigma_clipped_stats(finite, sigma=3.0, maxiters=5)
        if np.isfinite(sigma) and sigma > 0:
            levels = [median + n * sigma for n in _OVERVIEW_CONTOUR_SIGMA_LEVELS]
            ax.contour(
                mosaic_data, levels=levels, transform=ax.get_transform(mosaic_wcs), colors="C1"
            )

    _format_sky_axes(ax, ylabel=True)
    ax.set_title(
        f"{field_name}: true detections overview ({_provenance_backend(optical.provenance)})",
        size=14,
    )
    return fig


def build_true_detections_velocity_figure(
    mosaic_wcs: WCS, velocity_mosaic: np.ndarray, field_name: str
) -> Figure:
    """Field-wide plot of true detections, each one colored by its own systemic
    velocity (`postprocess.build_velocity_mosaic`) rather than flux -- so large-scale
    velocity structure across the field (e.g. detections clustering around a
    particular velocity, a hint of a group or cluster) is visible at a glance, not
    just spatial distribution -- direct user request; companion PNG to
    `postprocess.build_mosaic`'s `mosaic_true.fits`.

    `cmap="jet"` matches `build_validation_figure`'s per-source mom1 panel, so the
    same color consistently means the same velocity across every plot this pipeline
    produces. No optical background -- `velocity_mosaic`'s uncovered pixels are NaN
    (`postprocess.build_velocity_mosaic`), which `imshow` leaves transparent, so the
    field reads as "detections only" against a plain background.
    """
    fig = Figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection=mosaic_wcs)
    image = ax.imshow(velocity_mosaic, origin="lower", interpolation="nearest", cmap="jet")
    if np.isfinite(velocity_mosaic).any():
        colorbar = fig.colorbar(image, ax=ax, orientation="vertical", pad=0.01, aspect=30)
        colorbar.ax.set_ylabel(r"Velocity (km s$^{-1}$)")
    _format_sky_axes(ax, ylabel=True)
    ax.set_title(f"{field_name}: true detections by velocity", size=14)
    return fig
