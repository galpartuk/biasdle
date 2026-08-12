"""Title tracks per group, for the Heardle (audio) mode.

Hand-authored — but unlike a member list, a hallucinated song here cannot reach
the game: fetch_itunes.py has to find a matching track by the right artist or
the entry is dropped and reported. Treat the build report as the review pass.

Order within a group is roughly chronological; it has no gameplay meaning.
"""

SONGS = {
    "MAMAMOO": [
        "Um Oh Ah Yeh", "You're the Best", "Décalcomanie", "Yes I Am",
        "Starry Night", "Egotistic", "Gogobebe", "HIP", "Dingga", "AYA",
    ],
    "Red Velvet": [
        "Happiness", "Ice Cream Cake", "Dumb Dumb", "Russian Roulette",
        "Rookie", "Red Flavor", "Peek-A-Boo", "Bad Boy", "Power Up",
        "Zimzalabim", "Umpah Umpah", "Psycho", "Queendom", "Feel My Rhythm",
        "Birthday", "Chill Kill", "Cosmic",
    ],
    "GFRIEND": [
        "Glass Bead", "Me Gustas Tu", "Rough", "Navillera", "Fingertip",
        "Love Whisper", "Time for the Moon Night", "Sunrise", "Fever",
        "Apple", "MAGO",
    ],
    "OH MY GIRL": [
        "Cupid", "Closer", "Liar Liar", "Windy Day", "Coloring Book",
        "Secret Garden", "Remember Me", "Bungee", "Nonstop", "Dolphin",
        "Dun Dun Dance",
    ],
    "TWICE": [
        "Like OOH-AHH", "Cheer Up", "TT", "Knock Knock", "Signal", "Likey",
        "Heart Shaker", "What is Love?", "Dance the Night Away", "Yes or Yes",
        "FANCY", "Feel Special", "MORE & MORE", "I Can't Stop Me",
        "Alcohol-Free", "The Feels", "Talk that Talk", "SET ME FREE",
        "ONE SPARK", "Strategy",
    ],
    "WJSN": [
        "Secret", "I Wish", "Dreams Come True", "Save Me, Save You",
        "La La Love", "As You Wish", "UNNATURAL", "Last Sequence",
    ],
    "BLACKPINK": [
        "BOOMBAYAH", "Whistle", "Playing with Fire", "As If It's Your Last",
        "DDU-DU DDU-DU", "Kill This Love", "How You Like That",
        "Lovesick Girls", "Pink Venom", "Shut Down", "JUMP",
    ],
    "Dreamcatcher": [
        "Chase Me", "Good Night", "Fly High", "You and I", "What", "PIRI",
        "Scream", "BOCA", "Odd Eye", "BEcause", "MAISON", "VISION", "OOTD",
    ],
    "fromis_9": [
        "To Heart", "PITAPAT (DKDK)", "Love Bomb", "FUN!", "Feel Good (SECRET CODE)",
        "WE GO", "Talk & Talk", "DM", "Stay This Way", "#menow", "Supersonic",
    ],
    "(G)I-DLE": [
        "LATATA", "HANN", "Senorita", "Uh-Oh", "LION", "DUMDi DUMDi", "HWAA",
        "TOMBOY", "Nxde", "Queencard", "Super Lady", "Klaxon", "Fate",
    ],
    "LOONA": [
        "Hi High", "Butterfly", "So What", "Why Not?", "PTT (Paint The Town)",
        "Flip That",
    ],
    "ITZY": [
        "DALLA DALLA", "ICY", "WANNABE", "Not Shy", "마.피.아. In the morning",
        "LOCO", "SNEAKERS", "Cheshire", "CAKE", "BORN TO BE", "UNTOUCHABLE",
        "Girls Will Be Girls",
    ],
    "EVERGLOW": [
        "Bon Bon Chocolat", "Adios", "DUN DUN", "LA DI DA", "FIRST",
        "Pirate", "SLAY",
    ],
    "Rocket Punch": [
        "BIM BAM BUM", "BOUNCY", "JUICY", "Ring Ring", "CHIQUITA", "FLASH",
    ],
    "STAYC": [
        "SO BAD", "ASAP", "STEREOTYPE", "RUN2U", "BEAUTIFUL MONSTER",
        "Teddy Bear", "Bubble", "Cheeky Icy Thang", "GPT",
    ],
    "aespa": [
        "Black Mamba", "Next Level", "Savage", "Girls", "Spicy", "Drama",
        "Supernova", "Armageddon", "Whiplash", "Dirty Work",
    ],
    "Weeekly": ["Tag Me", "After School", "Holiday Party", "Ven Para"],
    "PURPLE KISS": [
        "Ponzona", "Zombie", "memeM", "Nerdy", "Sweet Juice", "BBB",
    ],
    "Billlie": [
        "RING X RING", "GingaMingaYo", "RING ma Bell", "snowy night", "EUNOIA",
    ],
    "IVE": [
        "ELEVEN", "LOVE DIVE", "After LIKE", "Kitsch", "I AM", "Baddie",
        "Either Way", "HEYA", "Accendio", "REBEL HEART", "ATTITUDE",
    ],
    "Kep1er": [
        "WA DA DA", "Up!", "We Fresh", "Back to the City", "Giddy",
        "Galileo", "Shooting Star", "Grand Prix", "TIPI-TAP",
    ],
    "NMIXX": [
        "O.O", "DICE", "Love Me Like This", "Roller Coaster", "DASH",
        "Party O'Clock", "KNOW ABOUT ME", "See that?",
    ],
    "LE SSERAFIM": [
        "FEARLESS", "ANTIFRAGILE", "UNFORGIVEN",
        "Eve, Psyche & the Bluebeard's wife", "Perfect Night", "EASY",
        "Smart", "CRAZY", "HOT",
    ],
    "NewJeans": [
        "Attention", "Hype Boy", "Cookie", "Ditto", "OMG", "Super Shy",
        "ETA", "Cool With You", "How Sweet", "Bubble Gum", "Supernatural",
    ],
    "tripleS": [
        "Rising", "Girls Never Die", "Hit the Floor", "Cherry Talk",
        "Generation",
    ],
    "KISS OF LIFE": [
        "Shhh", "Bad News", "Nobody Knows", "Sticky", "Get Loud", "Igloo",
    ],
    "BABYMONSTER": [
        "BATTER UP", "SHEESH", "Stuck In The Middle", "DRIP", "CLIK CLAK",
    ],
    "ILLIT": [
        "Magnetic", "Lucky Girl Syndrome", "Cherish (My Love)", "Tick-Tack",
        "Almond Chocolate", "Billyeoon Goyangi (Do the Dance)",
    ],
    "MEOVV": ["MEOW", "TOXIC", "HANDS UP", "BURNING UP"],
    "izna": ["IZNA", "SIGN", "BEEP"],
    "Hearts2Hearts": ["The Chase", "Style", "FOCUS"],
}

# Artist strings iTunes actually uses, where they differ from our display name.
# (G)I-DLE rebranded to "i-dle" in 2025 and Apple relabelled the back catalogue.
ITUNES_ARTIST = {
    "(G)I-DLE": ["i-dle", "(G)I-DLE", "GIDLE"],
    "WJSN": ["WJSN", "Cosmic Girls"],
    "fromis_9": ["fromis_9", "fromis 9"],
    "Rocket Punch": ["Rocket Punch"],
    "LOONA": ["LOONA", "이달의 소녀"],
    "tripleS": ["tripleS", "triple S"],
    "izna": ["izna", "IZNA"],
}
