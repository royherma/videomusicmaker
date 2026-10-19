// Phone layout (<= 700px): one screen, secondary controls in a More sheet, Rec hides every control for a screen recording.
const $ = (id) => document.getElementById(id);
const mq = matchMedia('(max-width:700px)');
const main = document.querySelector('main'), header = document.querySelector('header'), body = document.body;
const relayout = () => { dispatchEvent(new Event('resize')); requestAnimationFrame(() => center(true)); };

const sheet = Object.assign(document.createElement('div'), { id: 'sheet', hidden: true, innerHTML: '<div class="grab"></div><div class="sw"></div>' });
const scrim = Object.assign(document.createElement('div'), { id: 'scrim', hidden: true });
body.append(scrim, sheet);
const button = (id, text, title) => Object.assign(document.createElement('button'), { id, type: 'button', className: 'btn ph', textContent: text, title });
const rec = button('recBtn', 'Rec', 'Hides the controls and plays from the start, for a screen recording. Tap anywhere to bring them back.');
const more = button('moreBtn', 'More', 'Volume, pick, mp4, run, customize');
header.append(rec, more);

const moving = [...header.querySelectorAll('.switch'), $('flow'), $('deck'), $('facts'), $('build'), $('edit'), $('cb')].filter(Boolean);
const homes = moving.map((el) => { const mark = document.createComment(''); el.before(mark); return mark; });
const open = (on) => { sheet.hidden = scrim.hidden = !on; };
function place() {
  if (mq.matches) moving.forEach((el) => (el.classList.contains('switch') ? sheet.querySelector('.sw') : sheet).append(el));
  else { moving.forEach((el, i) => homes[i].after(el)); open(false); body.classList.remove('rec'); }
  relayout();
}
mq.addEventListener('change', place);
place();
more.onclick = () => open(true);
scrim.onclick = () => open(false);

rec.onclick = () => {
  $('back').click();
  body.classList.add('rec');
  scrollTo(0, 0);
  relayout();
  const toast = Object.assign(document.createElement('div'), { id: 'toast', textContent: 'Tap anywhere to bring the controls back' });
  body.append(toast);
  setTimeout(() => toast.remove(), 1700);
};
document.addEventListener('click', (e) => {
  if (!body.classList.contains('rec')) return;
  e.stopPropagation(); e.preventDefault();
  body.classList.remove('rec');
  $('tip').style.display = 'none';
  relayout();
}, true);

const video = $('video');
function shape() {
  if (!video.videoWidth) return;
  main.style.setProperty('--ar', `${video.videoWidth}/${video.videoHeight}`);
  main.classList.toggle('land', video.videoWidth / video.videoHeight > 1.1);
  relayout();
}
video.addEventListener('loadedmetadata', shape);
shape();

let shown;
function center(force) {
  const g = $('genres'), on = g.querySelector('.g.on');
  if (!mq.matches || !on || (on.dataset.id === shown && !force)) return;
  shown = on.dataset.id;
  g.scrollTo({ left: on.offsetLeft - g.offsetLeft - (g.clientWidth - on.offsetWidth) / 2, top: on.offsetTop - g.offsetTop - (g.clientHeight - on.offsetHeight) / 2, behavior: force ? 'instant' : 'smooth' });
}
new MutationObserver(() => center()).observe($('genres'), { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
