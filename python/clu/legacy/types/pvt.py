"""PVT implements a class to describe (position, velocity, time) triplets.

History:
2001-01-10 ROwen    Modified floatCnv to not handle NaN floating values,
    since this failed on Mac OS X; it will still handle string "NaN" (any case).
2002-08-08 ROwen    Modified to use new Astro.Tm functions which are in days, not sec.
2003-05-08 ROwen    Modified to use RO.CnvUtil.
2003-11-21 ROwen    Bug fix: __init__ did not check the data.
2005-06-08 ROwen    Changed PVT to a new-style class.
2007-07-02 ROwen    Added hasVel method.
2015-09-24 ROwen    Replace "== None" with "is None" to modernize the code.
2015-11-03 ROwen    Replace "!= None" with "is not None" to modernize the code.
"""

# type: ignore

import math
import time


__all__ = ["PVT"]


MJDJ2000 = 51544.5  # Modified Julian Date at epoch J2000.0 noon (days)
SecPerDay = 24.0 * 3600.0  # seconds per day
_UTCMinusTAIDays = -35 / float(SecPerDay)  # a reasonable value correct as of 2012-12
_TimeError = 0.0  # time reported by your computer's clock - actual time (seconds)
_TimeTupleJ2000 = (2000, 1, 1, 12, 0, 0, 5, 1, 0)


def getCurrPySec(uncorrTime=None):
    """Get current python time with time error correction applied

    Input:
    - uncorrTime: python time without correction applied; if None then current time is used

    """
    if uncorrTime is None:
        uncorrTime = time.time()
    return uncorrTime - _TimeError


def utcFromPySec(pySec=None):
    """Returns the UTC (MJD) corresponding to the supplied python time, or now if none."""

    if pySec is None:
        pySec = getCurrPySec()

    # python time (in seconds) corresponding to 2000-01-01 00:00:00
    # this is probably constant, but there's some chance
    # that on some computer systems it varies with daylights savings time
    pySecJ2000 = time.mktime(_TimeTupleJ2000) - time.timezone

    return MJDJ2000 + ((pySec - pySecJ2000) / SecPerDay)


def taiFromUTC(utc):
    """Convert UTC (MJD) to TAI (MJD)"""

    return utc - _UTCMinusTAIDays


def taiFromPySec(pySec=None):
    """Convert python seconds (now if None) to TAI (MJD)"""

    return taiFromUTC(utcFromPySec(pySec))


def asFloatOrNone(val):
    """Converts floats, integers and string representations of either to floats.
    If val is "NaN" (case irrelevant) or "?" returns None.

    Raises ValueError or TypeError for all other values

    """

    # check for NaN first in case ieee floating point is in use
    # (in which case float(val) would return something instead of failing)

    if hasattr(val, "lower") and val.lower() in ("nan", "?"):
        return None
    else:
        return float(val)


class PVT(object):
    """Defines a position, velocity, time triplet, where time is in TAI.

    Inputs:
    - pos   position
    - vel   velocity (in units of position/sec)
    - time  TAI, MJD seconds

    Each value must be one of: a float, a string representation of a float,
    "NaN" (any case) or None. "NaN" and None mean "unknown" and are stored as None.

    Raises ValueError if any value is invalid.
    """

    def __init__(self, pos=None, vel=0.0, t=0.0):
        self.pos = None
        self.vel = 0.0
        self.t = 0.0
        self.set(pos, vel, t)

    def __repr__(self):
        return "PVT(%s, %s, %s)" % (str(self.pos), str(self.vel), str(self.t))

    @property
    def native(self):
        """Returns a tuple of ``(pos, vel, t)``.

        For compatibility with other opscore types.

        """

        return (self.pos, self.vel, self.t)

    def getPos(self, t=None):
        """Returns the position at the specified time.
        Time defaults to the current TAI.

        Returns None if the pvt is invalid.
        """
        if not self.isValid():
            return None

        if t is None:
            t = taiFromPySec() * SecPerDay

        return self.pos + (self.vel * (t - self.t))

    def hasVel(self):
        """Return True if velocity is known and nonzero."""
        return self.vel not in (0, None)

    def isValid(self):
        """Returns True if the pvt is valid, False otherwise.

        A pvt is valid if all values are known (not None and finite) and time > 0.
        """
        return (
            (self.pos is not None)
            and math.isfinite(self.pos)
            and (self.vel is not None)
            and math.isfinite(self.vel)
            and (self.t is not None)
            and math.isfinite(self.t)
            and (self.t > 0)
        )

    def set(self, pos=None, vel=None, t=None):
        """Sets pos, vel and t; all default to their current values

        Each value must be one of: a float, a string representation of a float,
        "NaN" (any case) or None. "NaN" means "unknown" and is stored as None.

        Errors:
        Raises ValueError if any value is invalid.
        """
        if pos is not None:
            self.pos = asFloatOrNone(pos)
        if vel is not None:
            self.vel = asFloatOrNone(vel)
        if t is not None:
            self.t = asFloatOrNone(t)


if __name__ == "__main__":
    print("\nrunning PVT test")

    currTAI = taiFromPySec() * SecPerDay

    varList = (
        PVT(),
        PVT(25),
        PVT(25, 0, currTAI),
        PVT(25, 1),
        PVT(25, 1, currTAI),
        PVT("NaN", "NaN", "NaN"),
    )

    for i in range(5):
        t = taiFromPySec() * SecPerDay
        print("\ntime =", t)
        for var in varList:
            print(var, "pos =", var.getPos(t))
        if i < 4:
            time.sleep(1)
