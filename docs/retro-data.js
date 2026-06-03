// Sample data shaped like the live store feeds.
// Each product belongs to exactly one store. `prev` is the previous synced
// price; null means the item is newly added this run (NEW badge).
window.RETRO_STORES = [
  { id: "retrofam",   name: "RetroFam",     hue: 38  },  // amber
  { id: "retrovgames", name: "Retro vGames", hue: 192 },  // cyan
  { id: "lukiegames", name: "LukieGames",   hue: 330 },  // magenta
  { id: "dkoldies",   name: "DKOldies",     hue: 264 },  // violet
];

window.RETRO_DATA = [
  // ---- Nintendo 64 ----
  { id: 1,  name: "Super Mario 64",                         store: "retrofam",    platform: "Nintendo 64",   price: 39.99,  prev: 49.99 },
  { id: 2,  name: "GoldenEye 007",                          store: "lukiegames",  platform: "Nintendo 64",   price: 44.50,  prev: 41.00 },
  { id: 3,  name: "Mario Kart 64",                          store: "dkoldies",    platform: "Nintendo 64",   price: 34.99,  prev: 34.99 },
  { id: 4,  name: "The Legend of Zelda: Ocarina of Time",   store: "retrovgames", platform: "Nintendo 64",   price: 42.00,  prev: 55.00 },
  { id: 5,  name: "Banjo-Kazooie",                          store: "retrofam",    platform: "Nintendo 64",   price: 33.95,  prev: null  },
  { id: 6,  name: "Conker's Bad Fur Day",                   store: "lukiegames",  platform: "Nintendo 64",   price: 159.99, prev: 184.99 },
  { id: 7,  name: "Paper Mario",                            store: "dkoldies",    platform: "Nintendo 64",   price: 64.99,  prev: 59.99 },
  { id: 8,  name: "Star Fox 64",                            store: "retrovgames", platform: "Nintendo 64",   price: 28.50,  prev: 31.00 },

  // ---- Super Nintendo ----
  { id: 9,  name: "Super Mario World",                      store: "retrofam",    platform: "Super Nintendo", price: 29.99,  prev: 36.99 },
  { id: 10, name: "The Legend of Zelda: A Link to the Past", store: "lukiegames", platform: "Super Nintendo", price: 38.00,  prev: 38.00 },
  { id: 11, name: "Super Metroid",                          store: "dkoldies",    platform: "Super Nintendo", price: 54.99,  prev: 67.50 },
  { id: 12, name: "Donkey Kong Country",                    store: "retrovgames", platform: "Super Nintendo", price: 24.95,  prev: null  },
  { id: 13, name: "Chrono Trigger",                         store: "lukiegames",  platform: "Super Nintendo", price: 179.99, prev: 199.99 },
  { id: 14, name: "EarthBound",                             store: "dkoldies",    platform: "Super Nintendo", price: 199.00, prev: 189.00 },
  { id: 15, name: "Super Mario RPG: Legend of the Seven Stars", store: "retrofam", platform: "Super Nintendo", price: 72.00,  prev: 84.00 },
  { id: 16, name: "Final Fantasy III",                      store: "retrovgames", platform: "Super Nintendo", price: 58.50,  prev: 58.50 },

  // ---- Game Boy ----
  { id: 17, name: "Pokémon Red Version",                    store: "retrofam",    platform: "Game Boy",      price: 44.99,  prev: 52.99 },
  { id: 18, name: "Pokémon Yellow Version",                 store: "lukiegames",  platform: "Game Boy",      price: 49.99,  prev: 47.50 },
  { id: 19, name: "Tetris",                                 store: "dkoldies",    platform: "Game Boy",      price: 13.99,  prev: 16.99 },
  { id: 20, name: "Super Mario Land",                       store: "retrovgames", platform: "Game Boy",      price: 18.50,  prev: null  },
  { id: 21, name: "The Legend of Zelda: Link's Awakening",  store: "retrofam",    platform: "Game Boy",      price: 27.99,  prev: 32.00 },
  { id: 22, name: "Kirby's Dream Land",                     store: "lukiegames",  platform: "Game Boy",      price: 21.00,  prev: 21.00 },

  // ---- PlayStation 1 ----
  { id: 23, name: "Final Fantasy VII",                      store: "dkoldies",    platform: "PlayStation 1", price: 36.99,  prev: 44.99 },
  { id: 24, name: "Metal Gear Solid",                       store: "retrovgames", platform: "PlayStation 1", price: 42.50,  prev: 39.99 },
  { id: 25, name: "Crash Bandicoot",                        store: "retrofam",    platform: "PlayStation 1", price: 24.99,  prev: 29.99 },
  { id: 26, name: "Spyro the Dragon",                       store: "lukiegames",  platform: "PlayStation 1", price: 22.95,  prev: 22.95 },
  { id: 27, name: "Castlevania: Symphony of the Night",     store: "dkoldies",    platform: "PlayStation 1", price: 89.99,  prev: 109.99 },
  { id: 28, name: "Resident Evil 2",                        store: "retrovgames", platform: "PlayStation 1", price: 34.00,  prev: null  },
  { id: 29, name: "Tony Hawk's Pro Skater 2",               store: "retrofam",    platform: "PlayStation 1", price: 19.99,  prev: 23.50 },

  // ---- Sega Genesis ----
  { id: 30, name: "Sonic the Hedgehog 2",                   store: "lukiegames",  platform: "Sega Genesis",  price: 14.99,  prev: 17.99 },
  { id: 31, name: "Streets of Rage 2",                      store: "dkoldies",    platform: "Sega Genesis",  price: 39.99,  prev: 39.99 },
  { id: 32, name: "Gunstar Heroes",                         store: "retrovgames", platform: "Sega Genesis",  price: 64.50,  prev: 78.00 },
  { id: 33, name: "Phantasy Star IV",                       store: "retrofam",    platform: "Sega Genesis",  price: 119.99, prev: 134.99 },
  { id: 34, name: "Ecco the Dolphin",                       store: "lukiegames",  platform: "Sega Genesis",  price: 16.50,  prev: null  },
  { id: 35, name: "ToeJam & Earl",                          store: "dkoldies",    platform: "Sega Genesis",  price: 27.99,  prev: 25.00 },

  // ---- Dreamcast ----
  { id: 36, name: "Sonic Adventure",                        store: "retrovgames", platform: "Dreamcast",     price: 22.99,  prev: 26.99 },
  { id: 37, name: "Shenmue",                                store: "retrofam",    platform: "Dreamcast",     price: 49.99,  prev: 57.99 },
  { id: 38, name: "Crazy Taxi",                             store: "lukiegames",  platform: "Dreamcast",     price: 18.99,  prev: 18.99 },
  { id: 39, name: "Jet Grind Radio",                        store: "dkoldies",    platform: "Dreamcast",     price: 54.99,  prev: 62.50 },
  { id: 40, name: "Marvel vs. Capcom 2",                    store: "retrovgames", platform: "Dreamcast",     price: 99.99,  prev: 124.99 },
  { id: 41, name: "Skies of Arcadia",                       store: "retrofam",    platform: "Dreamcast",     price: 74.99,  prev: null  },
];
