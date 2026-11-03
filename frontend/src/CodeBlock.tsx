// Highlight trusted lesson examples as React text nodes: no HTML injection or code execution.
export default function CodeBlock({ code }: { code: string }) {
  const parts = code.split(/("[^"\n]*"|'[^'\n]*'|#[^\n]*|\b(?:def|return|if|elif|else|for|while|in|and|or|not|break|True|False|None)\b|\b\d+(?:\.\d+)?\b)/g)
  return <pre className="code-block"><code>{parts.map((part, i) => <span key={i} className={part.startsWith('#') ? 'code-comment' : /^["']/.test(part) ? 'code-string' : /^\d/.test(part) ? 'code-number' : /^(def|return|if|elif|else|for|while|in|and|or|not|break|True|False|None)$/.test(part) ? 'code-keyword' : ''}>{part}</span>)}</code></pre>
}
