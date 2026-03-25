"""Contains helper function used all over the plugin."""

import os
from pathlib import Path
import re

import wx  # pylint: disable=import-error
import wx.dataview  # pylint: disable=import-error

PLUGIN_PATH = Path(__file__).resolve().parent

EXCLUDE_FROM_POS = 2
EXCLUDE_FROM_BOM = 3


def getWxWidgetsVersion():
    """Get wx widgets version."""
    v = re.search(r"wxWidgets\s([\d\.]+)", wx.version())
    v = int(v.group(1).replace(".", ""))
    return v


def getVersion():
    """READ Version from file."""
    if not os.path.isfile(os.path.join(PLUGIN_PATH, "VERSION")):
        return "unknown"
    with open(os.path.join(PLUGIN_PATH, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def GetOS():
    """Get String with OS type."""
    return wx.PlatformInformation.Get().GetOperatingSystemIdName()


def GetScaleFactor(window):
    """Workaround if wxWidgets Version does not support GetDPIScaleFactor, for Mac OS always return 1.0."""
    if "Apple Mac OS" in GetOS():
        return 1.0
    if hasattr(window, "GetDPIScaleFactor"):
        return window.GetDPIScaleFactor()
    return 1.0


def HighResWxSize(window, size):
    """Workaround if wxWidgets Version does not support FromDIP."""
    if hasattr(window, "FromDIP"):
        return window.FromDIP(size)
    return size


def loadBitmapScaled(filename, scale=1.0, static=False):
    """Load a scaled bitmap, handle differences between Kicad versions."""
    if filename:
        path = os.path.join(PLUGIN_PATH, "icons", filename)
        bmp = wx.Bitmap(path)
        w, h = bmp.GetSize()
        img = bmp.ConvertToImage()
        if hasattr(wx.SystemSettings, "GetAppearance") and hasattr(
            wx.SystemSettings.GetAppearance, "IsUsingDarkBackground"
        ):
            if wx.SystemSettings.GetAppearance().IsUsingDarkBackground():
                img.Replace(0, 0, 0, 255, 255, 255)
            bmp = wx.Bitmap(img.Scale(int(w * scale), int(h * scale)))
    else:
        bmp = wx.Bitmap()
    if getWxWidgetsVersion() > 315 and not static:
        return wx.BitmapBundle(bmp)
    return bmp


def loadIconScaled(filename, scale=1.0):
    """Load a scaled icon, handle differences between Kicad versions."""
    bmp = loadBitmapScaled(filename, scale=scale, static=False)
    if getWxWidgetsVersion() > 315:
        return bmp
    return wx.Icon(bmp)


def natural_sort_collation(a, b):
    """Natural sort collation for use in sqlite."""
    if a == b:
        return 0

    def convert(text):
        return int(text) if text.isdigit() else text.lower()

    def alphanum_key(key):
        return [convert(c) for c in re.split("([0-9]+)", key)]

    natorder = sorted([a, b], key=alphanum_key)
    return -1 if natorder.index(a) == 0 else 1


def dict_factory(cursor, row) -> dict:
    """Row factory that returns a dict."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_lcsc_value(fp):
    """Get the first lcsc number (C123456 for example) from the properties of the footprint."""
    # KiCad 7.99
    try:
        for field in fp.GetFields():
            if re.match(r"lcsc|jlc", field.GetName(), re.IGNORECASE) and re.match(
                r"^C\d+$", field.GetText()
            ):
                return field.GetText()
    # KiCad <= V7
    except AttributeError:
        for key, value in fp.GetProperties().items():
            if re.match(r"lcsc|jlc", key, re.IGNORECASE) and re.match(r"^C\d+$", value):
                return value
    return ""


def set_lcsc_value(fp, lcsc: str):
    """Set an lcsc number to the first matching propertie of the footprint, use LCSC as property name if not found."""
    lcsc_field = None
    for field in fp.GetFields():
        if re.match(r"lcsc|jlc", field.GetName(), re.IGNORECASE) and re.match(
            r"^C\d+$", field.GetText()
        ):
            lcsc_field = field

    if lcsc_field:
        fp.SetField(lcsc_field.GetName(), lcsc)
    else:
        fp.SetField("LCSC", lcsc)
        # GetFieldByName was removed in KiCad 10; find the field by iterating
        for f in fp.GetFields():
            if f.GetName() == "LCSC":
                f.SetVisible(False)
                break


def get_dnp_value(fp):
    """Get DNP (Do Not Populate) status from footprint fields or native flag.

    Checks in order:
    1. Native IsDNP() flag (KiCad 7.99+)
    2. DNP field in footprint properties (KiCad 7.99+)
    3. DNP property key (KiCad <= V7)
    Returns True if the component should not be populated.
    """
    # Check native IsDNP flag first (KiCad 7.99+)
    if hasattr(fp, "IsDNP") and callable(fp.IsDNP) and fp.IsDNP():
        return True
    # Check fields for DNP parameter (KiCad 7.99+)
    try:
        for field in fp.GetFields():
            if field.GetName().upper() in ("DNP", "DO_NOT_POPULATE"):
                val = field.GetText().strip().upper()
                if val in ("1", "YES", "TRUE", "DNP"):
                    return True
    except AttributeError:
        # KiCad <= V7 - check properties
        try:
            for key, value in fp.GetProperties().items():
                if key.upper() in ("DNP", "DO_NOT_POPULATE"):
                    if value.strip().upper() in ("1", "YES", "TRUE", "DNP"):
                        return True
        except AttributeError:
            pass
    return False


def should_exclude_from_bom_or_pos(fp):
    """Check if footprint should be excluded from BOM/POS based on DNP parameter."""
    return get_dnp_value(fp) or get_exclude_from_bom(fp) or get_exclude_from_pos(fp)


def get_valid_footprints(board, max_ref_length=20):
    """Get all footprints that have a valid reference.

    Drop all REF** for example.
    Drop kibuzzard footprints and other invalid references (length check).
    The max_ref_length parameter defaults to 20, which is generous enough to
    support references like SDCARD-1 while still filtering out kibuzzard
    footprints which tend to have very long generated reference strings.
    """
    footprints = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if re.match(r"[\w\d-]+", ref) and len(ref) < max_ref_length:
            footprints.append(fp)
    return footprints


def get_bit(value, bit):
    """Get the nth bit of a byte."""
    return value & (1 << bit)


def toggle_bit(value, bit):
    """Toggle the nth bit of a byte."""
    return value ^ (1 << bit)


def get_exclude_from_pos(footprint):
    """Get the 'exclude from POS' property of a footprint."""
    if not footprint:
        return None
    val = footprint.GetAttributes()
    return bool(get_bit(val, EXCLUDE_FROM_POS))


def get_exclude_from_bom(footprint):
    """Get the 'exclude from BOM' property of a footprint."""
    if not footprint:
        return None
    val = footprint.GetAttributes()
    return bool(get_bit(val, EXCLUDE_FROM_BOM))


def toggle_exclude_from_pos(footprint):
    """Toggle the 'exclude from POS' property of a footprint."""
    if not footprint:
        return None
    val = footprint.GetAttributes()
    val = toggle_bit(val, EXCLUDE_FROM_POS)
    footprint.SetAttributes(val)
    return bool(get_bit(val, EXCLUDE_FROM_POS))


def toggle_exclude_from_bom(footprint):
    """Toggle the 'exclude from BOM' property of a footprint."""
    if not footprint:
        return None
    val = footprint.GetAttributes()
    val = toggle_bit(val, EXCLUDE_FROM_BOM)
    footprint.SetAttributes(val)
    return bool(get_bit(val, EXCLUDE_FROM_BOM))
