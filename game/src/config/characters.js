/**
 * Anime Artifact Hunter: Qahramon sinflari (Character classes)
 */

export const CHARACTER_CLASSES = {
  WARRIOR: {
    id: "warrior",
    name: "Jangchi (Swordman)",
    model: "/models/characters/swordman.glb",
    texture: "/textures/barbarian_texture.png",
    icon: "⚔️",
    speed: 5.2,
    attackPower: 24,
    attackRange: 2.0, // qilich zarbasi 2 metr masofagacha
    attackCooldown: 0.55,
    description: "Qilichbozlik va to'g'ridan-to'g'ri jangga ixtisoslashgan qudratli jangchi.",
  },
  MAGE: {
    id: "mage",
    name: "Sehrgar (Mage)",
    model: "/models/characters/Mage.glb",
    texture: "/textures/mage_texture.png",
    icon: "🔮",
    speed: 4.8,
    attackPower: 34,
    attackRange: 3.6,
    attackCooldown: 0.8,
    description: "Tabiat va sehr energiyasidan foydalanuvchi uzoq masofali afsungar.",
  },
  RANGER: {
    id: "ranger",
    name: "Mergan (Ranger)",
    model: "/models/characters/Ranger.glb",
    texture: "/textures/ranger_texture.png",
    icon: "🏹",
    speed: 5.6,
    attackPower: 28,
    attackRange: 4.2,
    attackCooldown: 0.7,
    description: "Chaqqon va uzoqdan aniq nishonga uruvchi ovchi kamonchi.",
  },
  ROGUE: {
    id: "rogue",
    name: "Qaroqchi (Rogue)",
    model: "/models/characters/Rogue_Hooded.glb",
    texture: "/textures/rogue_texture.png",
    icon: "🗡️",
    speed: 6.0,
    attackPower: 18,
    attackRange: 2.6,
    attackCooldown: 0.38,
    description: "Soya ichida yashirin harakatlanuvchi va tezkor zarbalar beruvchi.",
  },
};
