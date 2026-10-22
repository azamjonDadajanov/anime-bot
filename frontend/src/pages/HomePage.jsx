import { Link } from 'react-router-dom'
import useCatalogIndex from '../hooks/useCatalogIndex'
import Reveal from '../components/Reveal'
import SectionHead from '../components/SectionHead'
import MediaRail from '../components/MediaRail'
import { coverSrc } from '../apis/mediaUrl'
import {
  dateStamp,
  episodeLabel,
  formatScore,
  genreNames,
  ratingAverage,
  ratingVotes,
  releaseLabel,
  statusLabel,
  typeLabel,
} from '../mediaMeta'

const TYPE_TILES = [
  { key: 'anime', label: 'Animelar', jp: 'アニメ', icon: 'bi-stars', to: '/anime' },
  { key: 'movie', label: 'Filmlar', jp: '映画', icon: 'bi-film', to: '/movies' },
  { key: 'series', label: 'Seriallar', jp: 'ドラマ', icon: 'bi-collection-play', to: '/series' },
  { key: 'manga', label: 'Mangalar', jp: '漫画', icon: 'bi-journal-bookmark', to: '/manga' },
]

function handleParallax(event) {
  if (event.pointerType !== 'mouse') return
  const rect = event.currentTarget.getBoundingClientRect()
  const x = (event.clientX - rect.left) / rect.width - 0.5
  const y = (event.clientY - rect.top) / rect.height - 0.5
  event.currentTarget.style.setProperty('--px', x.toFixed(3))
  event.currentTarget.style.setProperty('--py', y.toFixed(3))
}

function Hero({ featured, counts, loading }) {
  if (loading) {
    return (
      <section className="hero-cinema">
        <div className="hero-skeleton" aria-hidden="true">
          <div className="hero-skeleton-lines">
            <div className="ac-skeleton hero-skeleton-line" />
            <div className="ac-skeleton hero-skeleton-line" />
            <div className="ac-skeleton hero-skeleton-line" />
            <div className="ac-skeleton hero-skeleton-line" />
            <div className="ac-skeleton hero-skeleton-line" />
          </div>
          <div className="ac-skeleton hero-skeleton-poster" />
        </div>
      </section>
    )
  }

  const cover = coverSrc(featured)
  const genres = genreNames(featured)

  return (
    <section className="hero-cinema" onPointerMove={handleParallax}>
      {cover && <img className="hero-backdrop" src={cover} alt="" aria-hidden="true" />}
      <span className="hero-veil" aria-hidden="true" />
      <span className="hero-scan" aria-hidden="true" />

      <div className="hero-rail">
        <div className="hero-meta-top">
          <span className="pill pill-live">Efirda · 2026</span>
          <span className="meta-coords">Toshkent · 41°18′N 69°14′E</span>
        </div>

        <div className="hero-copy">
          <div className="hero-kicker">
            <span className="dot" aria-hidden="true" />
            AniChopar / katalog indeksi
            <span className="hero-kicker-sep" aria-hidden="true">— 01</span>
          </div>

          <h1 className="hero-title">
            <span className="line">Har bir kadr —</span>
            <span className="line line-italic">yangi olam.</span>
          </h1>

          <p className="hero-text">
            Anime, kino, serial va manga. O&apos;zbek tilidagi katalog, yangi
            qismlar va sizga mos hikoyalar — bitta orbital platformada.
          </p>

          {featured && (
            <div className="hero-feature">
              <span className="hero-feature-label">Bugungi signal</span>
              <Link className="hero-feature-title" to={`/media/${featured.slug}`}>
                {featured.title}
              </Link>
              <span className="hero-feature-meta">
                <span>{typeLabel(featured)}</span>
                <span aria-hidden="true">·</span>
                <span>{releaseLabel(featured)}</span>
                {featured.rating ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span><i className="bi bi-star-fill" aria-hidden="true" /> {featured.rating}</span>
                  </>
                ) : null}
              </span>
            </div>
          )}

          <div className="hero-actions">
            <Link className="ac-btn ac-btn-primary" to={featured ? `/media/${featured.slug}` : '/explore'}>
              Hozir kashf etish <i className="bi bi-arrow-up-right" aria-hidden="true" />
            </Link>
            <Link className="ac-btn ac-btn-ghost" to="/explore">
              Katalogni ko&apos;rish <i className="bi bi-grid" aria-hidden="true" />
            </Link>
          </div>
        </div>

        <div className="hero-visual">
          <div className="hero-poster-frame">
            <Link
              className="hero-poster"
              to={featured ? `/media/${featured.slug}` : '/explore'}
              aria-label={featured ? `${featured.title} tafsilotlarini ochish` : 'Katalogni kashf etish'}
            >
              {cover
                ? <img src={cover} alt={featured ? `${featured.title} muqovasi` : ''} />
                : <span className="hero-poster-fallback"><i className="bi bi-stars" aria-hidden="true" /></span>}
              <span className="hero-poster-sheen" aria-hidden="true" />
              <span className="hero-poster-foot">
                <span>{featured ? typeLabel(featured) : 'Katalog'}</span>
                {featured?.rating ? (
                  <span className="rating"><i className="bi bi-star-fill" aria-hidden="true" /> {featured.rating}/10</span>
                ) : null}
              </span>
            </Link>

            <div className="hero-float-card card-top" aria-hidden="true">
              <b>{counts.total}</b>
              <span>Katalogdagi media</span>
            </div>
            <div className="hero-float-card card-bottom" aria-hidden="true">
              <b>{featured?.release_year || '2026'}</b>
              <span><i className="bi bi-broadcast" aria-hidden="true" /> Joriy mavsum</span>
            </div>
          </div>
          <span className="hero-visual-note">Chrome edition · AC / 26</span>
        </div>
      </div>

      <div className="hero-foot">
        <span className="hero-foot-left">
          <i className="scroll-tick" aria-hidden="true" />
          Pastga aylantiring — davom etamiz
        </span>
        <span className="hero-foot-genres">
          {(genres.length ? genres.slice(0, 3) : ['Anime', 'Kino', 'Manga']).map((genre) => (
            <span key={genre}>{genre}</span>
          ))}
          <span>· {episodeLabel(featured)}</span>
        </span>
      </div>
    </section>
  )
}

function SignalTicker({ genres }) {
  const items = [
    { label: "Yangi qismlar", jp: '新着' },
    { label: 'O\u2019zbek tilida', jp: '字幕' },
    { label: 'HD sifat', jp: '高画質' },
    ...genres.map((genre) => ({ label: genre.name, jp: genre.glyph })),
    { label: 'AniVoy AI', jp: '相棒' },
  ]

  return (
    <div className="signal-ticker" aria-label="Katalog signallari">
      <span className="signal-ticker-label">Signal</span>
      <div className="signal-ticker-viewport">
        <div className="signal-ticker-track">
          {[0, 1].map((copy) => (
            <div key={copy} aria-hidden={copy === 1 ? 'true' : undefined} style={{ display: 'flex' }}>
              {items.map((item, index) => (
                <span className="signal-ticker-item" key={`${copy}-${item.label}-${index}`}>
                  <span className="sep" aria-hidden="true">/</span>
                  <span className="jp" aria-hidden="true">{item.jp}</span>
                  {item.label}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function TypeIndex({ counts }) {
  return (
    <nav className="type-index" aria-label="Katalog turlari">
      {TYPE_TILES.map((tile, index) => (
        <Link className="type-tile" key={tile.key} to={tile.to}>
          <span className="type-tile-head">
            <span className="type-tile-code">{String(index + 1).padStart(2, '0')} / 04</span>
            <span className="type-tile-icon"><i className={`bi ${tile.icon}`} aria-hidden="true" /></span>
          </span>
          <span className="type-tile-glyph" aria-hidden="true">{tile.jp}</span>
          <span className="type-tile-body">
            <span className="type-tile-label">{tile.label}</span>
            <span className="type-tile-meta">
              <span>{counts[tile.key] || 0} ta media</span>
              <span aria-hidden="true">·</span>
              <span className="jp">{tile.jp}</span>
            </span>
          </span>
          <i className="bi bi-arrow-up-right type-tile-arrow" aria-hidden="true" />
        </Link>
      ))}
    </nav>
  )
}

function DropTimeline({ items }) {
  return (
    <div className="timeline-panel">
      <SectionHead
        index="01"
        title="Yangi translyatsiyalar"
        jp="新着"
        description="Katalogga eng so'nggi qo'shilgan media — birinchi bo'lib ko'ring."
        href="/latest"
        linkLabel="Hammasi"
      />
      {items.length ? (
        <ol className="drop-list">
          {items.map((item) => {
            const stamp = dateStamp(item.created_at)
            const cover = coverSrc(item)
            return (
              <li className="drop-row" key={item.id}>
                <time className="drop-date" dateTime={item.created_at}>
                  <b>{stamp.day}</b>
                  {stamp.month}
                </time>
                <span className="drop-thumb">
                  {cover
                    ? <img src={cover} alt="" loading="lazy" />
                    : <i className="bi bi-film" aria-hidden="true" />}
                </span>
                <span className="drop-body">
                  <Link className="drop-title" to={`/media/${item.slug}`}>{item.title}</Link>
                  <span className="drop-meta">
                    <span>{typeLabel(item)}</span>
                    <span className="dot" aria-hidden="true" />
                    <span>{statusLabel(item)}</span>
                    {genreNames(item).slice(0, 2).map((genre) => (
                      <span key={genre}>· {genre}</span>
                    ))}
                  </span>
                </span>
                <span className="drop-side">
                  {item.rating ? (
                    <span className="drop-rating">
                      <i className="bi bi-star-fill" aria-hidden="true" /> {item.rating}
                    </span>
                  ) : null}
                  <span className="drop-type">{releaseLabel(item)}</span>
                </span>
              </li>
            )
          })}
        </ol>
      ) : (
        <div className="empty-state compact-empty">
          <i className="bi bi-hourglass" aria-hidden="true" />
          <h3>Yangi qismlar kutilmoqda</h3>
          <p>Katalogga media qo&apos;shilgach shu yerda paydo bo&apos;ladi.</p>
        </div>
      )}
    </div>
  )
}

function RatingChart({ items }) {
  return (
    <aside className="chart-panel">
      <SectionHead
        index="02"
        title="Top reyting"
        jp="評価"
        description="Eng yuqori o'rtacha ball — teng natijada ko'proq ovoz olgani oldinda."
      />
      {items.length ? (
        <ol className="chart-list">
          {items.map((item, index) => {
            // The live 1-10 average, not the rounded legacy score: a title
            // with 128 votes at 8.6 stays above one with a single 9.
            const score = ratingAverage(item)
            const votes = ratingVotes(item)
            return (
              <li className="chart-row" key={item.id}>
                <span className="chart-rank">{String(index + 1).padStart(2, '0')}</span>
                <span className="chart-body">
                  <Link className="chart-title" to={`/media/${item.slug}`}>{item.title}</Link>
                  <span className="chart-bar" aria-hidden="true">
                    <span style={{ '--score': `${Math.min(100, (score || 0) * 10)}%` }} />
                  </span>
                </span>
                <span className="chart-score">
                  <b>{formatScore(score) || '—'}</b>
                  <i>{votes ? `${votes} baho` : "baho yo'q"}</i>
                </span>
              </li>
            )
          })}
        </ol>
      ) : (
        <p className="chart-empty">
          Hali media baholanmagan — birinchi bahoni siz qo&apos;ying.
        </p>
      )}
      <div className="chart-foot">
        <Link className="section-link" to="/popular">
          To&apos;liq reyting <i className="bi bi-arrow-right" aria-hidden="true" />
        </Link>
      </div>
    </aside>
  )
}

function SignalGrid({ items, counts, genreCount }) {
  const [hero, ...rest] = items
  if (!hero) return null
  const heroCover = coverSrc(hero)

  return (
    <section aria-label="Tanlangan signallar">
      <SectionHead
        index="03"
        title="Tanlangan signallar"
        jp="選集"
        description="Muharrir tanlovi: katalogdagi eng kuchli hikoyalar."
      />
      <div className="signal-grid">
        <Link className="signal-card signal-card-lg" to={`/media/${hero.slug}`}>
          {heroCover && <img src={heroCover} alt={`${hero.title} muqovasi`} loading="lazy" />}
          <span className="signal-card-copy">
            <span className="signal-card-kicker">Muharrir tanlovi · 01</span>
            <span className="signal-card-title">{hero.title}</span>
            <span className="signal-card-meta">
              <span>{typeLabel(hero)}</span>
              <span aria-hidden="true">·</span>
              <span>{releaseLabel(hero)}</span>
              {hero.rating ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span><i className="bi bi-star-fill" aria-hidden="true" /> {hero.rating}</span>
                </>
              ) : null}
              {genreNames(hero).length > 0 && (
                <>
                  <span aria-hidden="true">·</span>
                  <span>{genreNames(hero).slice(0, 2).join(' / ')}</span>
                </>
              )}
            </span>
          </span>
        </Link>

        {rest.slice(0, 2).map((item, index) => (
          <Link className="signal-card" to={`/media/${item.slug}`} key={item.id}>
            {coverSrc(item) && <img src={coverSrc(item)} alt={`${item.title} muqovasi`} loading="lazy" />}
            <span className="signal-card-copy">
              <span className="signal-card-kicker">Tanlov · 0{index + 2}</span>
              <span className="signal-card-title">{item.title}</span>
              <span className="signal-card-meta">
                <span>{typeLabel(item)}</span>
                {item.rating ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span><i className="bi bi-star-fill" aria-hidden="true" /> {item.rating}</span>
                  </>
                ) : null}
              </span>
            </span>
          </Link>
        ))}

        <div className="signal-note">
          <span className="note-mark" aria-hidden="true">次</span>
          <blockquote>
            Har bir kadr — yangi olam. Katalog cheksiz, tanlov sizniki.
          </blockquote>
          <div className="note-stats">
            <span><b>{counts.total}</b> media</span>
            <span><b>{genreCount}</b> janr</span>
            <span><b>04</b> format</span>
          </div>
        </div>
      </div>
    </section>
  )
}

function GenrePortals({ genres }) {
  if (!genres.length) return null
  return (
    <section aria-label="Janrlar bo'yicha kashf etish">
      <SectionHead
        index="04"
        title="Janr olamlari"
        jp="次元"
        description="Dimensional portallar: qaysi dunyoga kirasiz?"
        href="/explore"
        linkLabel="Barcha janrlar"
      />
      <div className="genre-portals">
        {genres.map((genre) => (
          <Link
            className="genre-portal"
            key={genre.name}
            to={`/explore?genre=${encodeURIComponent(genre.name)}`}
            style={{ '--hue': genre.hue }}
          >
            <span className="portal-top">
              <span className="portal-jp" aria-hidden="true">{genre.glyph}</span>
              <span className="portal-code">{genre.code}</span>
            </span>
            <span className="portal-body">
              <span className="portal-name">{genre.name}</span>
              <span className="portal-count">{genre.count} ta signal</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  )
}

function UpcomingBand({ items }) {
  if (!items.length) return null
  return (
    <section className="upcoming-band">
      <div className="upcoming-inner">
        <SectionHead
          index="05"
          title="Kutilayotgan translyatsiyalar"
          jp="予告"
          description="Hali efirga chiqmagan, lekin allaqachon katalogda."
          href="/upcoming"
          linkLabel="Barchasi"
        />
        <div className="upcoming-grid">
          {items.map((item) => (
            <Link className="upcoming-card" key={item.id} to={`/media/${item.slug}`}>
              <span className="upcoming-thumb">
                {coverSrc(item)
                  ? <img src={coverSrc(item)} alt="" loading="lazy" />
                  : <i className="bi bi-hourglass" aria-hidden="true" />}
              </span>
              <span className="upcoming-body">
                <span className="pill pill-accent">Kutilmoqda</span>
                <span className="upcoming-title">{item.title}</span>
                <span className="upcoming-meta">
                  <span>{typeLabel(item)}</span>
                  <span aria-hidden="true">·</span>
                  <span>{releaseLabel(item)}</span>
                  {item.rating ? <><span aria-hidden="true">·</span><span>{item.rating}/10</span></> : null}
                </span>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}

function HomeSkeleton() {
  return (
    <div aria-busy="true">
      <Hero loading />
      <div className="type-index" aria-hidden="true">
        {Array.from({ length: 4 }).map((_, index) => (
          <div className="type-tile" key={index}>
            <div className="ac-skeleton ac-skeleton-line" style={{ width: '40%' }} />
            <div className="ac-skeleton ac-skeleton-line" style={{ width: '72%', height: 24 }} />
          </div>
        ))}
      </div>
      <div className="home-stage" aria-hidden="true">
        <div className="timeline-panel">
          {Array.from({ length: 5 }).map((_, index) => (
            <div className="ac-skeleton ac-skeleton-line" key={index} style={{ height: 48, marginBottom: 8 }} />
          ))}
        </div>
        <div className="chart-panel">
          {Array.from({ length: 5 }).map((_, index) => (
            <div className="ac-skeleton ac-skeleton-line" key={index} style={{ height: 34, marginBottom: 8 }} />
          ))}
        </div>
      </div>
      <div className="poster-grid" aria-hidden="true">
        {Array.from({ length: 6 }).map((_, index) => (
          <div className="poster-card poster-card-skeleton" key={index}>
            <span className="poster-frame" />
          </div>
        ))}
      </div>
    </div>
  )
}

export function HomePage() {
  const {
    loading,
    error,
    reload,
    featured,
    latest,
    trending,
    top,
    editorial,
    upcoming,
    genres,
    counts,
  } = useCatalogIndex()

  return (
    <main className="dashboard-page home-page">
      {loading ? (
        <HomeSkeleton />
      ) : error ? (
        <>
          <Hero loading />
          <div className="empty-state home-error">
            <i className="bi bi-broadcast-pin" aria-hidden="true" />
            <h2>Signal uzildi</h2>
            <p>{error}</p>
            <button className="ac-btn ac-btn-ghost" type="button" onClick={reload}>
              Qayta urinish <i className="bi bi-arrow-clockwise" aria-hidden="true" />
            </button>
          </div>
        </>
      ) : (
        <>
          <Hero featured={featured} counts={counts} />
          <SignalTicker genres={genres} />

          <Reveal>
            <TypeIndex counts={counts} />
          </Reveal>

          <Reveal>
            <section className="home-stage">
              <DropTimeline items={latest} />
              <RatingChart items={top} />
            </section>
          </Reveal>

          <Reveal>
            <MediaRail
              title="Mashhurlar orbitasi"
              jp="人気"
              index="03"
              description="Eng yuqori reytingga ega media — bir ko'rishda tanlang."
              href="/popular"
              linkLabel="Barchasi"
              items={trending}
            />
          </Reveal>

          <Reveal>
            <SignalGrid items={editorial} counts={counts} genreCount={genres.length} />
          </Reveal>

          <Reveal>
            <GenrePortals genres={genres} />
          </Reveal>

          <Reveal>
            <UpcomingBand items={upcoming} />
          </Reveal>

          <Reveal>
            <section className="home-cta">
              <span className="eyebrow">AniChopar / Keyingi qadam</span>
              <h2 className="home-cta-title">
                Katalog cheksiz. <em>Tanlov sizniki.</em>
              </h2>
              <p className="home-cta-text">
                Janrlar, formatlar va kayfiyat bo&apos;yicha kashf eting — yoki
                shaxsiy kutubxonangizni to&apos;ldiring.
              </p>
              <div className="home-cta-actions">
                <Link className="ac-btn ac-btn-primary" to="/explore">
                  Kashf etishni boshlash <i className="bi bi-compass" aria-hidden="true" />
                </Link>
                <Link className="ac-btn ac-btn-ghost" to="/favorites">
                  Sevimlilarim <i className="bi bi-heart" aria-hidden="true" />
                </Link>
              </div>
            </section>
          </Reveal>
        </>
      )}
    </main>
  )
}

export default HomePage
