import logging
from dataclasses import dataclass
from math import pi, radians, tan
from typing import cast

from build123d import (
    Compound,
    Cone,
    Cylinder,
    Helix,
    Plane,
    Polygon,
    Pos,
    ShapeList,
    Transition,
    sweep,
)

_log = logging.getLogger(__name__)


def _as_compound(result: object) -> Compound:
    if isinstance(result, ShapeList):
        return Compound(children=list(result))
    return cast(Compound, result)


def _mesh_is_watertight(shape: Compound) -> bool:
    """True if *shape* tessellates to a closed manifold mesh (in-process).

    A watertight check without a file export, used to reject the non-watertight
    meshes OCC's helical thread booleans can produce at certain pitches — e.g.
    when a lead-in or run-out cone cuts across the thread — so the caller can
    nudge the pitch until the result is print-ready. Matches the watertight
    gate that :func:`print_scripts_tree_d.export.save_stl` applies on export.
    """
    import numpy as np
    import trimesh

    verts, tris = shape.tessellate(0.001)
    mesh = trimesh.Trimesh(
        vertices=np.array([(v.X, v.Y, v.Z) for v in verts]),
        faces=np.array(tris),
    )
    return bool(mesh.is_watertight)


def _thread_ridge(
    *,
    pitch: float,
    height: float,
    radius: float,
    depth: float,
    half_w: float,
    crest_half: float,
    skirt: float,
    outward: bool,
) -> Compound:
    """Sweep a trapezoidal thread ridge along a helix, centred at the origin.

    The tooth straddles the helix surface at ``radius``: a wide base (axial
    half-width ``half_w``) at the surface tapers to a flat crest of half-width
    ``crest_half`` at ``depth`` past the surface. Below the surface the profile
    continues as a straight ``skirt`` of width ``half_w`` buried ``skirt`` mm
    *into* the body — this thick overlap is what lets the ridge fuse to the
    core as a single solid (a thin 0.1 mm contact does not fuse reliably, and
    an unfused ridge gets dropped by the later intersect).

    The ridge is ADDED to a minor-diameter core (external) or SUBTRACTED from
    solid stock (internal); the caller trims the helical run-out flush with the
    body faces. This is far more robust than subtracting a groove capped at the
    faces — that meets the flat face almost tangentially and tessellates
    non-watertight, worsening with turn count (long bodies / small pitch).
    ``Transition.ROUND`` keeps the swept solid clean through every turn.

    Args:
        pitch:
            Axial distance between crests in mm.
        height:
            Body length the helix spans in mm.
        radius:
            Radius of the surface the ridge straddles — the minor (core)
            radius for an external thread, the bore radius for an internal one.
        depth:
            Radial thread depth in mm (surface to crest).
        half_w:
            Axial half-width of the tooth at the surface (root) in mm.
        crest_half:
            Axial half-width of the flat crest in mm (< half_w).
        skirt:
            Radial depth the base is buried into the body for a clean fuse, mm.
        outward:
            True builds the ridge radially outward; False inward.
    Returns:
        The swept ridge solid, centred on the body at the origin.
    """
    sign = 1.0 if outward else -1.0
    helix = Helix(pitch=pitch, height=height, radius=radius)
    # Local x is radial (+ = away from the surface, scaled by `sign`); y is
    # axial. Buried skirt (x in [-skirt, 0], width half_w) → tooth flank
    # (x in [0, depth], half_w → crest_half) → flat crest at x = depth.
    profile = Plane(
        origin=helix @ 0.0, z_dir=helix % 0.0, x_dir=(1, 0, 0)
    ) * Polygon(
        (-skirt * sign, -half_w),
        (0.0, -half_w),
        (depth * sign, -crest_half),
        (depth * sign, crest_half),
        (0.0, half_w),
        (-skirt * sign, half_w),
        align=None,
    )
    swept = sweep(
        profile,  # type: ignore[arg-type]
        path=helix,
        is_frenet=True,
        transition=Transition.ROUND,
    )
    return _as_compound(Pos(0, 0, -height / 2.0) * swept)


def _build_thread(
    *,
    external: bool,
    outer_r: float,
    surface_r: float,
    bore_r: float,
    thickness: float,
    pitch: float,
    depth: float,
    half_w: float,
    crest_half: float,
) -> Compound:
    """Build a threaded body, retrying off OCC sweep degeneracies.

    External: a thread ridge is fused onto a minor-diameter core and the
    helical run-out trimmed flush. Internal: the ridge (valley material) is
    subtracted from solid stock and the minor bore drilled. A few specific
    turn counts (``thickness / pitch``) make OCC's sweep/boolean collapse to an
    empty or thread-less result; we validate the volume lands in the expected
    band and, if not, nudge the pitch <2 % to shift the turn count off the
    degeneracy. ``surface_r`` is the radius the thread straddles (the minor
    radius for external, the bore radius for internal).

    Args:
        external:
            True for an external ridge, False for an internal (nut) thread.
        outer_r, surface_r, bore_r, thickness, pitch, depth, half_w, crest_half:
            Thread geometry; see :func:`make_screw_part`.
    Returns:
        The threaded body, centred at the origin.
    Raises:
        ValueError: If no nudge yields valid geometry (pitch too fine for the
            length at this diameter).
    """
    if external:
        core_vol = pi * surface_r**2 * thickness
        solid_vol = pi * outer_r**2 * thickness
        core = Cylinder(surface_r, thickness)
        skirt = min(2.0 * depth, 0.7 * surface_r)
    else:
        # Nut: valid volume sits below the un-threaded tube (grooves remove).
        tube_vol = pi * (outer_r**2 - bore_r**2) * thickness
        skirt = min(0.5 * bore_r, 0.5)

    for factor in (1.0, 1.008, 0.992, 1.017, 0.984, 1.027):
        p = pitch * factor
        try:
            ridge = _thread_ridge(
                pitch=p,
                height=thickness,
                radius=surface_r,
                depth=depth,
                half_w=half_w,
                crest_half=crest_half,
                skirt=skirt,
                outward=True,
            )
            if external:
                body = _as_compound(
                    (core + ridge) & Cylinder(outer_r + 1e-3, thickness)
                )
                # Lower bound rejects the degeneracies (empty result, or a
                # ridge that failed to fuse and got dropped — volume ~= core);
                # loose upper bound is a sanity guard only.
                ok = core_vol * 1.001 < body.volume < solid_vol * 1.05
            else:
                stock = _as_compound(Cylinder(outer_r, thickness) - ridge)
                body = _as_compound(stock - Cylinder(bore_r, thickness + 2))
                ok = 0.3 * tube_vol < body.volume < tube_vol * 1.001
        except Exception:
            ok = False
        if ok:
            if factor != 1.0:
                _log.warning(
                    "thread_pitch %.3g hit an OCC sweep degeneracy at this "
                    "length; nudged to %.4g to build a clean thread.",
                    pitch,
                    p,
                )
            return body

    raise ValueError(
        f"could not build a watertight thread for thread_pitch {pitch} at "
        f"thickness {thickness} (≈{thickness / pitch:.0f} turns); OCC's helical "
        f"sweep fails at this turn count — use a coarser thread_pitch or a "
        f"shorter thickness."
    )


def _thread_profile(
    *,
    pitch: float,
    angle: float,
    depth: float,
    crest_width: float,
    root_width: float,
    outer_r: float,
    outer_diameter: float,
) -> tuple[float, float, float]:
    """Resolve a trapezoidal thread cross-section to (depth, half_w, crest_half).

    The profile derives entirely from ``pitch`` plus a default V-form; every
    other value is an *independent override* of one dimension, so you pass only
    what you need and they never conflict — each dimension has exactly one
    source (the explicit value, or the derived default):

      ``depth``       radial height           (default 0.6 * pitch)
      ``angle``       flank V-angle; seeds the tooth base (default 60 deg)
      ``root_width``  root flat; sets the tooth base directly and takes
                      precedence over ``angle`` for the flank
      ``crest_width`` crest flat              (default a quarter of the base)

    Returns the half-width of the tooth base (``half_w``) and crest
    (``crest_half``). Overrides are clamped to keep the trapezoid valid
    (base < pitch, crest <= base, depth <= 0.45 * radius); a clamp or a
    redundant spec warns.
    """
    # Radial depth.
    if depth > 0:
        d = min(depth, 0.45 * outer_r)
        if d < depth:
            _log.warning(
                "thread_depth %.3g exceeds 0.45 * radius; clamped to %.3g.",
                depth,
                d,
            )
    else:
        unclamped = 0.6 * pitch
        d = min(unclamped, 0.35 * outer_r)
        if d < unclamped:
            _log.warning(
                "thread_pitch %.3g is coarse for diameter %.3g; thread depth "
                "clamped to %.3g.",
                pitch,
                outer_diameter,
                d,
            )
    # Tooth base half-width (the flank). root_width sets it directly and wins
    # over angle; angle only seeds it when no root_width is given.
    if root_width > 0:
        base_hw = (pitch - root_width) / 2.0
        if abs(angle - 60.0) > 1e-9:
            _log.warning(
                "thread_root_width set; thread_angle %.3g is ignored for the "
                "flank.",
                angle,
            )
    else:
        base_hw = d * tan(radians(angle / 2.0))
    # Cap so adjacent turns never overlap (2*half_w < pitch) and the flank fits
    # the radius — overlapping teeth make the helical sweep self-intersect.
    half_w = min(base_hw, 0.45 * outer_r, 0.48 * pitch)
    if half_w < base_hw and root_width <= 0:
        _log.warning(
            "thread_angle %.3g / pitch %.3g make the flank too wide; half-width "
            "clamped to %.3g (effective angle reduced).",
            angle,
            pitch,
            half_w,
        )
    # Crest flat half-width.
    if crest_width > 0:
        crest_half = min(crest_width / 2.0, 0.95 * half_w)
        if crest_width / 2.0 > 0.95 * half_w:
            _log.warning(
                "thread_crest_width %.3g is not narrower than the tooth base; "
                "clamped to %.3g.",
                crest_width,
                2.0 * crest_half,
            )
    else:
        crest_half = 0.25 * half_w
    return d, half_w, crest_half


@dataclass(frozen=True)
class ThreadProfile:
    """A thread cross-section spec, built via a factory so the inputs for one
    thread form cannot conflict with another's.

    Use a constructor instead of the bare ``thread_*`` arguments of
    :func:`make_screw_part` / :func:`make_threaded_rod` when you want the spec
    to be conflict-proof by construction — each factory takes only its own
    form's inputs, so you cannot mix (say) an angle and a root width:

      * :meth:`v_thread` — a V / truncated-V thread whose flank is set by an
        angle, with optional depth / crest overrides.
      * :meth:`trapezoidal` — a square / ACME / measured thread defined directly
        by its flat widths and depth (no angle; the flank follows the widths).

    Pass the result as the ``thread`` argument. Fields mirror the resolver in
    :func:`_thread_profile`; 0 means "derive".
    """

    pitch: float
    angle: float = 60.0
    depth: float = 0.0
    crest_width: float = 0.0
    root_width: float = 0.0

    @classmethod
    def v_thread(
        cls,
        pitch: float,
        angle: float = 60.0,
        depth: float = 0.0,
        crest_width: float = 0.0,
    ) -> "ThreadProfile":
        """V / truncated-V thread; the flank is set by ``angle``. ``depth`` and
        ``crest_width`` override their derived defaults (0 = derive)."""
        return cls(
            pitch=pitch, angle=angle, depth=depth, crest_width=crest_width
        )

    @classmethod
    def trapezoidal(
        cls,
        pitch: float,
        depth: float,
        crest_width: float,
        root_width: float,
    ) -> "ThreadProfile":
        """Square / ACME / measured thread; the flat widths and depth define the
        profile directly (the flank angle follows from them, no ``angle``)."""
        return cls(
            pitch=pitch,
            depth=depth,
            crest_width=crest_width,
            root_width=root_width,
        )


def make_washer(
    outer_diameter: float, hole_diameter: float, thickness: float
) -> Compound:
    """Create a flat washer (annular disc) centred at the origin.

    Args:
        outer_diameter:
            Overall diameter of the washer in mm.
        hole_diameter:
            Diameter of the central hole in mm. Must be less than outer_diameter.
        thickness:
            Thickness of the washer along the Z axis in mm.
    Returns:
        A washer-shaped compound (outer cylinder minus inner cylinder).
    Raises:
        ValueError: If hole_diameter >= outer_diameter.
    """
    if hole_diameter >= outer_diameter:
        raise ValueError(
            f"hole_diameter ({hole_diameter}) must be less than outer_diameter ({outer_diameter})."
        )
    body = Cylinder(outer_diameter / 2, thickness)
    hole = Cylinder(hole_diameter / 2, thickness)
    return body - hole


def make_magnet(outer_diameter: float, thickness: float) -> Compound:
    """Create a cylindrical magnet centred at the origin.

    Args:
        outer_diameter:
            Diameter of the magnet in mm.
        thickness:
            Thickness of the magnet along the Z axis in mm.
    Returns:
        A cylindrical magnet-shaped compound.
    """
    return Cylinder(outer_diameter / 2, thickness)


def make_screw_part(
    outer_diameter: float,
    thickness: float,
    thread_pitch: float = 0.0,
    bore_diameter: float = 0.0,
    thread_angle: float = 60.0,
    lead_in_length: float = 0.0,
    lead_in_tip_diameter: float = 0.0,
    internal_thread: bool = False,
    thread_depth: float = 0.0,
    thread_crest_width: float = 0.0,
    thread_root_width: float = 0.0,
    thread: "ThreadProfile | None" = None,
) -> Compound:
    """Create a screw-shaped part centred at the origin.

    Produces an external thread (ridge on the outside) by default, or an
    internal threaded bore (nut / threaded insert) when ``internal_thread=True``.
    An optional lead-in chamfer tapers the tip of an external screw to ease
    thread engagement.

    The thread profile needs only ``thread_pitch``: ``thread_angle``,
    ``thread_depth``, ``thread_crest_width`` and ``thread_root_width`` are
    independent overrides of one dimension each, so pass only what you need and
    they will not conflict (``thread_root_width`` takes precedence over
    ``thread_angle`` for the flank). See :func:`_thread_profile`. For a
    conflict-proof spec, pass a :class:`ThreadProfile` as ``thread`` instead
    (e.g. ``ThreadProfile.trapezoidal(...)``); it overrides the ``thread_*``
    arguments.

    Args:
        outer_diameter:
            Outer body diameter in mm. For external thread this is the crest
            diameter; for internal thread this is the outer body wall.
        thickness:
            Length along the Z axis in mm.
        thread_pitch:
            Axial distance between thread crests in mm. 0 makes a smooth
            cylinder (or smooth bore for internal_thread=True).
        bore_diameter:
            For external thread: optional central through-bore in mm. 0 leaves
            solid; must be < outer_diameter.
            For internal thread: the bore that receives the thread. Required
            (> 0); must be < outer_diameter.
        thread_angle:
            Included V-angle of the thread profile in degrees. 60 = ISO metric;
            55 = Whitworth. Controls flank width relative to thread depth.
        lead_in_length:
            Chamfer length at the insertion tip (bottom face) in mm; 0 = no
            chamfer. The outer surface tapers from outer_diameter down to
            lead_in_tip_diameter over this length. Applies to external thread
            only; capped at half of thickness.
        lead_in_tip_diameter:
            Outer diameter at the very tip of the lead-in in mm. 0 defaults to
            the thread root diameter (or a 45° taper when thread_pitch=0). Must
            be < outer_diameter.
        internal_thread:
            If True, cut a helical groove into the bore wall instead of raising
            an external ridge. bore_diameter must be > 0.
        thread_depth:
            Radial thread height (crest to root) in mm. 0 derives it as
            0.6 * thread_pitch. Use it to match a measured minor diameter:
            thread_depth = (outer_diameter - minor_diameter) / 2.
        thread_crest_width:
            Axial width of the flat at the thread crest (tip) in mm. 0 derives
            it from the tooth base. Must be narrower than the tooth base.
        thread_root_width:
            Axial width of the flat at the thread root (valley) in mm. 0 derives
            the tooth from thread_angle; otherwise the tooth base width is
            thread_pitch - thread_root_width (overrides thread_angle).
        thread:
            A :class:`ThreadProfile` (built via ``ThreadProfile.v_thread`` or
            ``ThreadProfile.trapezoidal``) defining the whole thread profile in
            a conflict-proof way. When given it overrides thread_pitch and every
            thread_* argument.
    Returns:
        A screw-shaped compound centred at the origin (Z is the axis).
    Raises:
        ValueError: For invalid or geometrically impossible parameter combinations.
    """
    if thread is not None:
        # A ThreadProfile fully defines the profile and overrides the thread_*
        # arguments — the factory already guaranteed the inputs are consistent.
        thread_pitch = thread.pitch
        thread_angle = thread.angle
        thread_depth = thread.depth
        thread_crest_width = thread.crest_width
        thread_root_width = thread.root_width

    if outer_diameter <= 0:
        raise ValueError(f"outer_diameter must be > 0, got {outer_diameter}")
    if thickness <= 0:
        raise ValueError(f"thickness must be > 0, got {thickness}")
    if thread_pitch < 0:
        raise ValueError(f"thread_pitch must be >= 0, got {thread_pitch}")
    if bore_diameter < 0:
        raise ValueError(f"bore_diameter must be >= 0, got {bore_diameter}")
    if bore_diameter >= outer_diameter:
        raise ValueError(
            f"bore_diameter ({bore_diameter}) must be < outer_diameter ({outer_diameter})"
        )
    if not (0.0 < thread_angle < 180.0):
        raise ValueError(
            f"thread_angle must be in (0, 180) degrees, got {thread_angle}"
        )
    if lead_in_length < 0:
        raise ValueError(f"lead_in_length must be >= 0, got {lead_in_length}")
    if lead_in_tip_diameter < 0:
        raise ValueError(
            f"lead_in_tip_diameter must be >= 0, got {lead_in_tip_diameter}"
        )
    if lead_in_tip_diameter >= outer_diameter:
        raise ValueError(
            f"lead_in_tip_diameter ({lead_in_tip_diameter}) must be < "
            f"outer_diameter ({outer_diameter})"
        )
    if internal_thread and bore_diameter == 0:
        raise ValueError("bore_diameter must be > 0 when internal_thread=True")

    outer_r = outer_diameter / 2.0

    # Clamp lead_in_length to half thickness so there is always some full-
    # diameter body remaining above the chamfer.
    max_lead = thickness * 0.5
    if lead_in_length > max_lead:
        _log.warning(
            "lead_in_length %.3g exceeds half of thickness (%.3g); clamped.",
            lead_in_length,
            max_lead,
        )
        lead_in_length = max_lead

    # --- Thread geometry (one resolver; shared by internal and external) ---
    root_r = outer_r  # updated below when thread_pitch > 0
    depth = 0.0
    half_w = 0.0
    crest_half = 0.0
    if thread_pitch > 0:
        depth, half_w, crest_half = _thread_profile(
            pitch=thread_pitch,
            angle=thread_angle,
            depth=thread_depth,
            crest_width=thread_crest_width,
            root_width=thread_root_width,
            outer_r=outer_r,
            outer_diameter=outer_diameter,
        )
        root_r = outer_r - depth  # minor radius for external thread

    # --- Build body ---
    if internal_thread:
        bore_r = bore_diameter / 2.0

        if thread_pitch == 0:
            # Smooth bore — no thread groove.
            screw = _as_compound(
                Cylinder(outer_r, thickness) - Cylinder(bore_r, thickness + 2)
            )
        else:
            if bore_r + depth >= outer_r:
                raise ValueError(
                    f"bore_diameter ({bore_diameter}) plus thread depth "
                    f"({2 * depth:.3g} mm) reaches or exceeds outer_diameter "
                    f"({outer_diameter}); increase outer_diameter or reduce "
                    f"bore_diameter / thread_pitch."
                )
            # Subtract a trapezoidal thread ridge (the valley material, built
            # outward from the bore wall into the stock) then bore out the
            # minor diameter. Drilling the full bore trims the run-out flush,
            # keeping the result watertight at any turn count.
            screw = _build_thread(
                external=False,
                outer_r=outer_r,
                surface_r=bore_r,
                bore_r=bore_r,
                thickness=thickness,
                pitch=thread_pitch,
                depth=depth,
                half_w=half_w,
                crest_half=crest_half,
            )

        root_r = bore_r  # used below for lead-in tip default

    else:
        # --- External thread ---
        if thread_pitch == 0:
            screw = _as_compound(Cylinder(outer_r, thickness))
        else:
            # Build the thread as a ridge ADDED onto a minor-diameter core,
            # then trim the helical run-out flush with an intersect. Adding a
            # ridge (vs subtracting a groove) and clipping flat at the faces
            # keeps the mesh watertight even at high turn counts (long bodies,
            # small pitch), where the groove approach left non-watertight
            # slivers at the end faces.
            screw = _build_thread(
                external=True,
                outer_r=outer_r,
                surface_r=root_r,
                bore_r=0.0,
                thickness=thickness,
                pitch=thread_pitch,
                depth=depth,
                half_w=half_w,
                crest_half=crest_half,
            )

        # --- Lead-in chamfer at the insertion tip ---
        if lead_in_length > 0:
            if lead_in_tip_diameter > 0.0:
                tip_r = lead_in_tip_diameter / 2.0
            elif thread_pitch > 0:
                tip_r = root_r  # taper to thread root diameter
            else:
                tip_r = max(0.0, outer_r - lead_in_length)  # 45° taper

            if tip_r >= outer_r:
                _log.warning(
                    "lead_in_tip_diameter %.3g is not smaller than outer_diameter; "
                    "lead-in chamfer skipped.",
                    lead_in_tip_diameter,
                )
            else:
                # Extend the intersection solid 1 mm past each body face so
                # no face of (chamfer + upper) is coincident with the screw
                # body — coincident faces cause OCC artefacts.
                _extra = 1.0
                taper_rate = (outer_r - tip_r) / lead_in_length
                tip_r_ext = max(0.0, tip_r - taper_rate * _extra)
                cone_h = lead_in_length + _extra
                cone_z = -thickness / 2 - _extra + cone_h / 2
                chamfer = Pos(0, 0, cone_z) * Cone(tip_r_ext, outer_r, cone_h)
                # Full-diameter cylinder above the chamfer zone, 1 mm past top.
                upper_h = thickness - lead_in_length
                upper = Pos(0, 0, lead_in_length / 2 + _extra / 2) * Cylinder(
                    outer_r + 1.0, upper_h + _extra
                )
                screw = _as_compound(screw & _as_compound(chamfer + upper))

        # Optional central bore (external mode only). Done after lead-in so
        # the bore cuts through the final chamfered shape rather than leaving
        # inner edge artefacts where the cone boundary meets the hollow bore.
        if bore_diameter > 0:
            bore_r_ext = bore_diameter / 2.0
            if bore_r_ext >= root_r:
                _log.warning(
                    "bore_diameter %.3g reaches past the thread root (%.3g); the "
                    "core wall is gone, leaving only the thread ridges.",
                    bore_diameter,
                    2 * root_r,
                )
            screw = _as_compound(screw - Cylinder(bore_r_ext, thickness + 2))

    return screw


def make_threaded_rod(
    outer_diameter: float,
    thickness: float,
    smooth_length: float,
    thread_pitch: float = 0.0,
    bore_diameter: float = 0.0,
    thread_angle: float = 60.0,
    thread_depth: float = 0.0,
    thread_crest_width: float = 0.0,
    thread_root_width: float = 0.0,
    lead_in_length: float = 0.0,
    lead_in_tip_diameter: float = 0.0,
    runout_length: float = 0.0,
    thread: "ThreadProfile | None" = None,
) -> Compound:
    """Create a rod with a smooth shank and an externally threaded end.

    A two-part single object: the bottom ``smooth_length`` mm is a plain full-
    diameter shank, and the remaining length (top, +Z) carries an external
    thread cut to the same crest diameter. This is what a partially-threaded
    bolt or a screw-in insert looks like.

    Built as one watertight solid by generating a full-length external thread
    (via :func:`make_screw_part`) and burying its lower turns under a full-
    diameter collar — the collar *is* the smooth shank. Boolean-fusing two
    separately-threaded solids into one body is unreliable in OCC; threading
    once over the whole length and hiding the lower turns stays watertight at
    every turn count ``make_screw_part`` itself supports. The collar is a hair
    (1e-3 mm) proud of the crests so it shares no cylindrical face with them —
    coincident crest faces would make the union non-watertight.

    Args:
        outer_diameter:
            Outer (thread crest) diameter in mm.
        thickness:
            Overall length along the Z axis in mm.
        smooth_length:
            Length of the smooth shank at the bottom (-Z) in mm. Must be > 0 and
            < thickness; the remainder (top, +Z) is threaded.
        thread_pitch:
            Axial distance between thread crests in mm. Must be > 0.
        bore_diameter:
            Optional central through-bore in mm. 0 leaves it solid; must be
            < outer_diameter.
        thread_angle:
            Included V-angle of the thread profile in degrees (60 = ISO metric).
        thread_depth:
            Radial thread height (crest to root) in mm; see
            :func:`make_screw_part`. 0 derives it as 0.6 * thread_pitch.
        thread_crest_width:
            Axial width of the thread crest flat in mm; 0 derives it.
        thread_root_width:
            Axial width of the thread root flat in mm; 0 derives the tooth from
            thread_angle. With pitch + depth + crest + root widths you can match
            a measured trapezoidal/square thread exactly.
        lead_in_length:
            Chamfer length at the threaded tip (+Z) in mm; 0 = none. The thread
            crests taper down to lead_in_tip_diameter over this length so the
            screw starts easily into a mating part. Capped at half the thickness.
        lead_in_tip_diameter:
            Outer diameter at the very tip of the lead-in in mm; 0 defaults to
            the thread root (minor) diameter. Must be < outer_diameter.
        runout_length:
            Length in mm over which the thread fades out into the smooth shank
            (a tapered run-out at the shank transition); 0 = abrupt. Capped at
            the threaded length.
        thread:
            A :class:`ThreadProfile` defining the whole thread profile in a
            conflict-proof way; when given it overrides thread_pitch and every
            thread_* argument (so thread_pitch need not be passed separately).
    Returns:
        A two-part rod compound centred at the origin; threaded end at +Z.
    Raises:
        ValueError: For invalid or geometrically impossible parameter
            combinations.

    A lead-in or run-out cone cuts across the helical thread, which OCC can
    tessellate non-watertight at some pitches; when either taper is requested
    the pitch-nudge retry additionally verifies the mesh is watertight in-
    process, so the returned solid is always print-ready.
    """
    if thread is not None:
        thread_pitch = thread.pitch
        thread_angle = thread.angle
        thread_depth = thread.depth
        thread_crest_width = thread.crest_width
        thread_root_width = thread.root_width

    if outer_diameter <= 0:
        raise ValueError(f"outer_diameter must be > 0, got {outer_diameter}")
    if thickness <= 0:
        raise ValueError(f"thickness must be > 0, got {thickness}")
    if thread_pitch <= 0:
        raise ValueError(
            f"thread_pitch must be > 0 for a threaded rod, got {thread_pitch}; "
            f"pass thread_pitch or a thread=ThreadProfile spec."
        )
    if not (0.0 < smooth_length < thickness):
        raise ValueError(
            f"smooth_length must be > 0 and < thickness ({thickness}), got "
            f"{smooth_length}; use make_screw_part for a fully threaded part."
        )
    if bore_diameter < 0:
        raise ValueError(f"bore_diameter must be >= 0, got {bore_diameter}")
    if bore_diameter >= outer_diameter:
        raise ValueError(
            f"bore_diameter ({bore_diameter}) must be < outer_diameter "
            f"({outer_diameter})"
        )
    if not (0.0 < thread_angle < 180.0):
        raise ValueError(
            f"thread_angle must be in (0, 180) degrees, got {thread_angle}"
        )
    if lead_in_length < 0:
        raise ValueError(f"lead_in_length must be >= 0, got {lead_in_length}")
    if lead_in_tip_diameter < 0:
        raise ValueError(
            f"lead_in_tip_diameter must be >= 0, got {lead_in_tip_diameter}"
        )
    if lead_in_tip_diameter >= outer_diameter:
        raise ValueError(
            f"lead_in_tip_diameter ({lead_in_tip_diameter}) must be < "
            f"outer_diameter ({outer_diameter})"
        )
    if runout_length < 0:
        raise ValueError(f"runout_length must be >= 0, got {runout_length}")

    outer_r = outer_diameter / 2.0
    collar_z = -thickness / 2.0 + smooth_length / 2.0
    shank_top = -thickness / 2.0 + smooth_length
    lead = min(lead_in_length, 0.45 * thickness)
    runout = min(runout_length, thickness - smooth_length)
    has_taper = lead > 0 or runout > 0

    if bore_diameter > 0:
        eff_depth0 = (
            min(thread_depth, 0.45 * outer_r)
            if thread_depth > 0
            else min(0.6 * thread_pitch, 0.35 * outer_r)
        )
        if bore_diameter / 2.0 >= outer_r - eff_depth0:
            _log.warning(
                "bore_diameter %.3g reaches past the thread root (%.3g); the "
                "core wall is gone, leaving only the thread ridges.",
                bore_diameter,
                2 * (outer_r - eff_depth0),
            )

    # The collar→thread fuse (and any taper cone cutting across the thread) can
    # fail for specific turn counts (thickness / pitch): the collar stays a
    # separate solid or the mesh tessellates with holes. We detect that in-
    # process — solids != 1, or (with a taper) a non-watertight mesh — and dodge
    # it by nudging the pitch < 4 % to shift the turn count.
    for factor in (1.0, 1.008, 0.992, 1.017, 0.984, 1.027, 1.04, 0.96):
        pitch = thread_pitch * factor
        try:
            eff_depth = (
                min(thread_depth, 0.45 * outer_r)
                if thread_depth > 0
                else min(0.6 * pitch, 0.35 * outer_r)
            )
            root_r = outer_r - eff_depth
            threaded = make_screw_part(
                outer_diameter=outer_diameter,
                thickness=thickness,
                thread_pitch=pitch,
                thread_angle=thread_angle,
                thread_depth=thread_depth,
                thread_crest_width=thread_crest_width,
                thread_root_width=thread_root_width,
            )
            rod = _as_compound(
                threaded
                + Pos(0, 0, collar_z) * Cylinder(outer_r + 1e-3, smooth_length)
            )
            # Run-out: a cone fading the thread out into the shank. It overlaps
            # 0.4 mm into the collar so the two fuse cleanly.
            if runout > 0:
                rc_h = runout + 0.4
                rod = _as_compound(
                    rod
                    + Pos(0, 0, shank_top - 0.4 + rc_h / 2.0)
                    * Cone(outer_r + 1e-3, root_r, rc_h)
                )
            # Lead-in chamfer at the threaded tip (+Z): intersect with a cone +
            # under-cylinder (mirror of make_screw_part's tip chamfer). Done on
            # the solid, before boring.
            if lead > 0:
                tip_r = (
                    lead_in_tip_diameter / 2.0
                    if lead_in_tip_diameter > 0
                    else root_r
                )
                _e = 1.0
                rate = (outer_r - tip_r) / lead
                tip_ext = max(0.0, tip_r - rate * _e)
                cone_h = lead + _e
                chamfer = Pos(0, 0, thickness / 2 + _e - cone_h / 2) * Cone(
                    outer_r, tip_ext, cone_h
                )
                lower = Pos(0, 0, -(lead / 2 + _e / 2)) * Cylinder(
                    outer_r + 1.0, (thickness - lead) + _e
                )
                trimmed = rod & _as_compound(chamfer + lower)
                if trimmed is None:
                    continue
                rod = _as_compound(trimmed)
            if bore_diameter > 0:
                rod = _as_compound(
                    rod - Cylinder(bore_diameter / 2.0, thickness + 2)
                )
            good = len(rod.solids()) == 1 and (
                not has_taper or _mesh_is_watertight(rod)
            )
        except Exception:
            good = False
        if not good:
            continue
        if factor != 1.0:
            _log.warning(
                "thread_pitch %.3g hit an OCC degeneracy at this length; nudged "
                "to %.4g to keep the rod watertight.",
                thread_pitch,
                pitch,
            )
        return rod

    raise ValueError(
        f"could not build a watertight threaded rod for thread_pitch "
        f"{thread_pitch} at thickness {thickness} (≈{thickness / thread_pitch:.0f} "
        f"turns); OCC's helical booleans fail at this turn count — use a "
        f"slightly different thread_pitch, thickness, or taper length."
    )
