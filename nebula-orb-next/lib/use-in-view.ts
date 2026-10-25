export function observeActivity(element: Element, setActive: (active: boolean) => void) {
  if (typeof IntersectionObserver === 'undefined') { setActive(true); return () => {}; }
  const observer = new IntersectionObserver(([entry]) => setActive(Boolean(entry?.isIntersecting)), { threshold: 0.01 });
  observer.observe(element);
  return () => observer.disconnect();
}
