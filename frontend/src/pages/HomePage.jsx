import { useState, useEffect } from 'react'
import { Button, Text, Title } from '@mantine/core'
import { Link } from 'react-router-dom'
import MediaRail from '../components/MediaRail'
import { SpotlightCard, SpotlightSkeleton } from '../components/SpotlightCard'
import { mediaApi } from '../apis/api'
import { sections, sectionOrder } from '../mediaSections'

const categoryTiles = [
  { label: 'Filmlar', icon: 'bi-film', to: '/movies' },
  { label: 'Animelar', icon: 'bi-stars', to: '/anime' },
  { label: 'Seriallar', icon: 'bi-tv', to: '/series' },
  { label: 'Mangalar', icon: 'bi-book', to: '/manga' },
  { label: 'Mashhurlar', icon: 'bi-fire', to: '/popular' },
  { label: 'Kutilmoqda', icon: 'bi-hourglass-split', to: '/upcoming' },
]

function Spotlight() {
  const [item, setItem] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    mediaApi.popular()
      .then((data) => {
        if (!active) return
        const list = Array.isArray(data) ? data : data.results || []
        setItem(list[0] || null)
      })
      .catch(() => active && setItem(null))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  if (loading) return <SpotlightSkeleton />
  return <SpotlightCard item={item} />
}

function HomeHero() {
  return (
    <section className="home-hero">
      <div className="home-hero-copy">
        <Text className="eyebrow">KINO TOP / KATALOG</Text>
        <Title order={1} className="home-hero-title">
          Sevimli <b>kino</b>, <b>anime</b> va <b>manga</b>lar — bir joyda
        </Title>
        <Text c="dimmed" className="home-hero-text">
          Yangi qo'shilganlar, mashhurlar va kutilayotgan kontentni kashf eting.
          O'zbek tilida, yuqori sifatda.
        </Text>
        <div className="home-hero-cta">
          <Button
            component={Link}
            to="/movies"
            size="md"
            radius="xl"
            rightSection={<i className="bi bi-arrow-right" aria-hidden="true" />}
          >
            Katalogni ko'rish
          </Button>
          <Button
            component={Link}
            to="/favorites"
            size="md"
            radius="xl"
            variant="default"
            leftSection={<i className="bi bi-heart" aria-hidden="true" />}
          >
            Sevimlilarim
          </Button>
        </div>
        <ul className="home-hero-pills">
          <li><i className="bi bi-collection-play" aria-hidden="true" /> Kino · Anime · Serial · Manga</li>
          <li><i className="bi bi-globe2" aria-hidden="true" /> O'zbek tilida</li>
          <li><i className="bi bi-badge-hd" aria-hidden="true" /> HD sifat</li>
        </ul>
      </div>
      <Spotlight />
    </section>
  )
}

export function HomePage() {
  return (
    <main className="dashboard-page">
      <HomeHero />
      <nav className="category-tiles" aria-label="Tezkor bo'limlar">
        {categoryTiles.map((tile) => (
          <Link key={tile.to} className="category-tile" to={tile.to}>
            <i className={`bi ${tile.icon} category-tile-icon`} aria-hidden="true" />
            <span className="category-tile-label">{tile.label}</span>
            <i className="bi bi-arrow-up-right category-tile-arrow" aria-hidden="true" style={{marginRight: 10}} />
          </Link>
        ))}
      </nav>
      <div className="home-rails">
        {sectionOrder.map((key) => {
          const section = sections[key]
          return (
            <MediaRail
              key={key}
              title={section.title}
              load={section.load}
              href={section.href}
            />
          )
        })}
      </div>
    </main>
  )
}

export default HomePage
