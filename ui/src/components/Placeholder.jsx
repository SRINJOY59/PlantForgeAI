export default function Placeholder({ icon: Icon, title, children }) {
  return (
    <div className="grid h-full place-items-center px-6 text-center">
      <div className="max-w-sm">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-steel-50 text-steel-600 dark:bg-steel-950">
          <Icon size={24} />
        </div>
        <h1 className="mt-4 text-lg font-semibold">{title}</h1>
        <p className="mt-1.5 text-sm muted">{children}</p>
      </div>
    </div>
  );
}
