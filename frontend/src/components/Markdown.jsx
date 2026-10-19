import { Fragment, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { parseMarkdown } from '../markdown'

// The assistant answers in markdown; this renders it as real HTML elements
// (paragraphs, lists, quotes, code) instead of showing the raw markers. The
// parser returns data and every run below is built with React, so a model that
// writes "<script>" still ends up as visible text.

function Inline({ nodes }) {
  return nodes.map((node, index) => {
    if (node.type === 'strong') {
      return (
        <strong key={index}>
          <Inline nodes={node.children} />
        </strong>
      )
    }
    if (node.type === 'em') {
      return (
        <em key={index}>
          <Inline nodes={node.children} />
        </em>
      )
    }
    if (node.type === 'del') {
      return (
        <del key={index}>
          <Inline nodes={node.children} />
        </del>
      )
    }
    if (node.type === 'code') {
      return (
        <code key={index} className="md-code">
          {node.value}
        </code>
      )
    }
    if (node.type === 'link') {
      // Catalogue links are paths inside the app; open them without a reload.
      if (node.href.startsWith('/')) {
        return (
          <Link key={index} to={node.href} className="md-link">
            <Inline nodes={node.children} />
          </Link>
        )
      }
      return (
        <a
          key={index}
          href={node.href}
          className="md-link"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Inline nodes={node.children} />
        </a>
      )
    }
    return <Fragment key={index}>{node.value}</Fragment>
  })
}

function Lines({ lines }) {
  return lines.map((line, index) => (
    <Fragment key={index}>
      {index > 0 && <br />}
      <Inline nodes={line} />
    </Fragment>
  ))
}

function Block({ block }) {
  if (block.type === 'paragraph') {
    return (
      <p>
        <Lines lines={block.lines} />
      </p>
    )
  }
  if (block.type === 'heading') {
    return (
      <p className="md-heading">
        <Inline nodes={block.content} />
      </p>
    )
  }
  if (block.type === 'list') {
    const List = block.ordered ? 'ol' : 'ul'
    return (
      <List>
        {block.items.map((item, index) => (
          <li key={index}>
            <Inline nodes={item} />
          </li>
        ))}
      </List>
    )
  }
  if (block.type === 'quote') {
    return (
      <blockquote>
        <Lines lines={block.lines} />
      </blockquote>
    )
  }
  if (block.type === 'code') {
    return (
      <pre className="md-pre">
        <code>{block.text}</code>
      </pre>
    )
  }
  return <hr />
}

export default function Markdown({ text, className }) {
  const blocks = useMemo(() => parseMarkdown(text), [text])
  return (
    <div className={className}>
      {blocks.map((block, index) => (
        <Block block={block} key={index} />
      ))}
    </div>
  )
}
