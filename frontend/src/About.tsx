import { version } from '../package.json'

export const AUTHOR_SIGNATURE = 'Made by Kusymbaev Alan'

export function AuthorSignature() {
  return <p className="author-signature">{AUTHOR_SIGNATURE}</p>
}

export function AboutApp() {
  return <section className="panel settings-panel about-panel" aria-labelledby="about-heading">
    <h3 id="about-heading">О приложении</h3>
    <dl className="about-details">
      <div><dt>Название</dt><dd>Academy AI</dd></div>
      <div><dt>Автор</dt><dd>Kusymbaev Alan</dd></div>
      <div><dt>Назначение</dt><dd>Персональная образовательная платформа</dd></div>
      <div><dt>Версия приложения</dt><dd>{version}</dd></div>
    </dl>
    <div><h4>Основные технологии</h4><ul className="about-technologies" aria-label="Основные технологии">
      <li>React · TypeScript · Vite</li>
      <li>Python · FastAPI · SQLModel · Alembic</li>
      <li>SQLite · PostgreSQL · Supabase Auth</li>
      <li>PWA · IndexedDB</li>
    </ul></div>
    <AuthorSignature />
  </section>
}
