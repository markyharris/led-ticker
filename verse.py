# Random New Testament Bible verses for the ticker (MicroPython).
#
# Verses are bundled on the board (King James Version - public
# domain), so this subject needs no network at all. One verse is
# picked per cycle; the segment scrolls "REF - text" across the
# sign. All text is plain ASCII: the sign's 8x8 font has no
# curly quotes or em dashes.
#
# The pick function is pure (takes an optional index) so the
# rotation can be unit-tested on a desktop.

VERSES = [
    ("John 3:16",
     "For God so loved the world, that he gave his only begotten "
     "Son, that whosoever believeth in him should not perish, but "
     "have everlasting life."),
    ("Matthew 11:28",
     "Come unto me, all ye that labour and are heavy laden, and "
     "I will give you rest."),
    ("John 14:27",
     "Peace I leave with you, my peace I give unto you: not as "
     "the world giveth, give I unto you."),
    ("Philippians 4:13",
     "I can do all things through Christ which strengtheneth me."),
    ("Romans 8:28",
     "And we know that all things work together for good to them "
     "that love God."),
    ("Matthew 6:33",
     "But seek ye first the kingdom of God, and his righteousness; "
     "and all these things shall be added unto you."),
    ("John 8:12",
     "I am the light of the world: he that followeth me shall not "
     "walk in darkness, but shall have the light of life."),
    ("Romans 15:13",
     "Now the God of hope fill you with all joy and peace in "
     "believing."),
    ("Philippians 4:6",
     "Be careful for nothing; but in every thing by prayer and "
     "supplication with thanksgiving let your requests be made "
     "known unto God."),
    ("Matthew 5:16",
     "Let your light so shine before men, that they may see your "
     "good works, and glorify your Father which is in heaven."),
    ("John 10:10",
     "I am come that they might have life, and that they might "
     "have it more abundantly."),
    ("Romans 12:12",
     "Rejoicing in hope; patient in tribulation; continuing "
     "instant in prayer;"),
    ("1 John 4:8",
     "He that loveth not knoweth not God; for God is love."),
    ("Matthew 28:20",
     "Lo, I am with you alway, even unto the end of the world."),
    ("John 16:33",
     "These things I have spoken unto you, that in me ye might "
     "have peace. In the world ye shall have tribulation: but be "
     "of good cheer; I have overcome the world."),
    ("2 Timothy 1:7",
     "For God hath not given us the spirit of fear; but of power, "
     "and of love, and of a sound mind."),
]


def pick(index=None):
    """One (reference, text) pair. With an index, that verse;
    without one, a random verse (urandom when available)."""
    if index is None:
        try:
            import urandom
            index = urandom.getrandbits(8) % len(VERSES)
        except ImportError:
            import time
            index = time.ticks_ms() % len(VERSES)
    return VERSES[index % len(VERSES)]


def segment(index=None):
    """Segment text for the sign, or None if the list is empty."""
    if not VERSES:
        return None
    ref, text = pick(index)
    return "%s - %s" % (ref, text)
