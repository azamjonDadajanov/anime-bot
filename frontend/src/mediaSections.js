import { mediaApi } from './apis/api'

export const sections = {
  latest: {
    title: "So'ngi yuklanganlar",
    eyebrow: 'KINO TOP / YANGI',
    description: "Katalogga eng so'nggi qo'shilgan media.",
    load: mediaApi.latest,
    href: '/latest',
  },
  popular: {
    title: 'Mashhurlar',
    eyebrow: 'KINO TOP / TOP',
    description: "Eng yuqori reytingga ega media.",
    load: mediaApi.popular,
    href: '/popular',
  },
  upcoming: {
    title: "Birinchilardan bo'ling",
    eyebrow: 'KINO TOP / KUTILMOQDA',
    description: "Tez orada chiqadigan media — birinchilardan bo'lib ko'ring.",
    load: mediaApi.upcoming,
    href: '/upcoming',
  },
  movies: {
    title: 'Filmlar',
    eyebrow: 'KINO TOP / KINO',
    description: 'Katalogdagi barcha filmlar.',
    load: mediaApi.movies,
    href: '/movies',
  },
  anime: {
    title: 'Animelar',
    eyebrow: 'KINO TOP / ANIME',
    description: 'Katalogdagi barcha animelar.',
    load: mediaApi.anime,
    href: '/anime',
  },
  manga: {
    title: 'Mangalar',
    eyebrow: 'KINO TOP / MANGA',
    description: 'Katalogdagi barcha mangalar.',
    load: mediaApi.manga,
    href: '/manga',
  },
  series: {
    title: 'Seriallar',
    eyebrow: 'KINO TOP / SERIAL',
    description: 'Katalogdagi barcha seriallar.',
    load: mediaApi.series,
    href: '/series',
  },
  random: {
    title: 'Tasodifiy',
    eyebrow: 'KINO TOP / TASODIFIY',
    description: 'Tasodifiy tanlangan media.',
    load: mediaApi.random,
  },
}

export const sectionOrder = ['latest', 'popular', 'upcoming', 'movies', 'anime', 'manga', 'series', 'random']
