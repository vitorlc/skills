// Executed inside page.evaluate; anchor on accessible controls, not translated row labels.
export function readPassengerCounts() {
  const counts = {};
  const labels = {
    Adultos: 'Adicionar adulto',
    Crianças: 'Adicionar criança de 2 a 11 anos',
    'Bebês no assento': 'Adicionar bebê em assento',
    'Bebês no colo': 'Adicionar bebê de colo',
  };
  for (const [kind, label] of Object.entries(labels)) {
    const button = [...document.querySelectorAll('button[aria-label]')].find(el => el.getAttribute('aria-label') === label && el.getClientRects().length);
    let row = button?.parentElement;
    for (let depth = 0; row && depth < 5; depth++, row = row.parentElement) {
      if (row.querySelectorAll('button').length !== 2) continue;
      const numbers = [...row.querySelectorAll('*')]
        .filter(el => el.children.length === 0 && !el.closest('button') && /^\d+$/.test(el.textContent.trim()))
        .map(el => Number(el.textContent.trim()));
      // Google duplicates the count in an accessibility/live-region span.
      const unique = [...new Set(numbers)];
      if (unique.length === 1) { counts[kind] = unique[0]; break; }
    }
  }
  return counts;
}
