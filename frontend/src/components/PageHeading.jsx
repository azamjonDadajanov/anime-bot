function PageHeading({ eyebrow, title, description, stats }) {
  return (
    <header className="page-intro">
      <div className="page-intro-main">
        <span className="eyebrow">{eyebrow}</span>
        <h1 className="page-intro-title">{title}</h1>
        {description && <p className="page-intro-sub">{description}</p>}
      </div>
      {stats?.length > 0 && (
        <div className="page-intro-side">
          {stats.map((stat) => (
            <div key={stat.label}>
              <b>{stat.value}</b>
              {stat.label}
            </div>
          ))}
        </div>
      )}
    </header>
  )
}

export default PageHeading
