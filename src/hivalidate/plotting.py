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

- Continuum panel display range is computed from the cutout's own robust statistics
  (mean +/- 3 sigma, matching what the optical panel already did), not the legacy
  script's hardcoded `vmin=-0.0001, vmax=0.00025` (right for one continuum image,
  wrong for any other survey/field).
- Provenance (which optical/continuum backend actually supplied each cutout) is
  annotated directly on the figure, since there are now multiple possible sources
  per panel (PLAN.md section 5, "Provenance").
- The optical panel displays an RGB cutout (`optical.data.ndim == 3`) as-is, with no
  greyscale vmin/vmax applied -- see `cutouts/optical.py`'s `LegacySurveyBackend`,
  whose grz Lupton composite already comes correctly coloured and stretched.

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
from astropy.table import Row, Table
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


def _robust_vlim(data: np.ndarray, n_sigma: float = 3.0) -> tuple[float, float]:
    """mean +/- n_sigma*std, falling back to (0, 1) for degenerate (all-equal or
    all-NaN) data -- avoids a matplotlib warning/blank image on a placeholder cutout.
    """
    finite = data[np.isfinite(data)]
    if finite.size == 0 or finite.std() == 0:
        return 0.0, 1.0
    return finite.mean() - n_sigma * finite.std(), finite.mean() + n_sigma * finite.std()


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

    fig = Figure(figsize=(18, 11))
    fig.subplots_adjust(left=0.05, right=0.98, wspace=0.1)

    # --- panel 1: optical + mom0 contours ---
    ax_opt = fig.add_subplot(231, projection=display_wcs)
    if optical is not None:
        if optical.data.ndim == 3:
            # An RGB composite (currently only LegacySurveyBackend's grz Lupton
            # composite -- see cutouts/optical.py) already comes pre-stretched and
            # colour-balanced; re-applying our own greyscale vmin/vmax on top would
            # both discard its colour and redo a worse version of the stretch it
            # already did.
            ax_opt.imshow(optical.data, origin="lower", interpolation="nearest")
        else:
            vmin, vmax = _robust_vlim(optical.data)
            ax_opt.imshow(
                optical.data,
                origin="lower",
                interpolation="nearest",
                cmap="Greys",
                vmin=vmin,
                vmax=vmax,
            )
        ax_opt.contour(
            col_density_map, levels=contour_levels_scaled, transform=ax_opt.get_transform(mom0_wcs)
        )
        ellipse = Ellipse(
            _beam_location(display_wcs),
            cubelets.beam_maj_arcsec / 3600,
            cubelets.beam_min_arcsec / 3600,
            angle=cubelets.beam_pa_deg,
            fc="C3",
            ec="C3",
            alpha=0.5,
            transform=ax_opt.get_transform("fk5"),
        )
        ax_opt.add_patch(ellipse)
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
        vmin, vmax = _robust_vlim(continuum.data)
        ax_cont.imshow(
            continuum.data,
            origin="lower",
            interpolation="nearest",
            cmap="afmhot",
            vmin=vmin,
            vmax=vmax,
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


def _beam_location(wcs: WCS) -> tuple[float, float]:
    """Sky position for the beam ellipse -- bottom-left corner of the displayed
    cutout, matching the legacy script's placement.
    """
    ra, dec = wcs.celestial.array_index_to_world_values(20, 20)
    return float(ra), float(dec)


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
