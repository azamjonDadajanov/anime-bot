import { Link } from 'react-router-dom'

function SectionHead({ index, title, jp, description, href, linkLabel = "Barchasini ko'rish" }) {
  return (
    <div className="section-head">
      <div className="section-head-main">
        <h2 className="section-title">
          {index && <span className="section-index">{index}</span>}
          <span>{title}</span>
          {jp && <span className="jp" aria-hidden="true">{jp}</span>}
        </h2>
        {description && <p className="section-sub">{description}</p>}
      </div>
      {href && (
        <Link className="section-link" to={href}>
          {linkLabel} <i className="bi bi-arrow-right" aria-hidden="true" />
        </Link>
      )}
    </div>
  )
}

export default SectionHead
