export function Placeholder({ title, description }: { title: string; description: string }) {
  return (
    <section className="placeholder-card">
      <p className="eyebrow">F0 FOUNDATION</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </section>
  );
}
