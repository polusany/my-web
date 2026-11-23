const menuToggle = document.querySelector('.menu-toggle');
const mainNavigation = document.getElementById('main-navigation');

if (menuToggle && mainNavigation) {
  const closeMenu = () => {
    menuToggle.setAttribute('aria-expanded', 'false');
    menuToggle.setAttribute('aria-label', 'Open navigation menu');
    mainNavigation.classList.remove('is-open');
  };

  menuToggle.addEventListener('click', () => {
    const isOpen = menuToggle.getAttribute('aria-expanded') === 'true';
    menuToggle.setAttribute('aria-expanded', String(!isOpen));
    menuToggle.setAttribute('aria-label', isOpen ? 'Open navigation menu' : 'Close navigation menu');
    mainNavigation.classList.toggle('is-open', !isOpen);
  });

  mainNavigation.querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMenu));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMenu();
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 700) closeMenu();
  });
}


const stateSelect = document.getElementById('state');
const townSelect = document.getElementById('town');
const typeSelect = document.getElementById('title');
const form = document.getElementById('property-form');
const errorBox = document.getElementById('form-error');
const submitButton = document.getElementById('submit-button');
const resultStatus = document.getElementById('result-status');
const emptyResult = document.getElementById('empty-result');
const priceResult = document.getElementById('price-result');
let metadata = null;

function setOptions(select, values, placeholder) {
  select.replaceChildren();
  const first = document.createElement('option');
  first.value = '';
  first.textContent = placeholder;
  select.append(first);
  values.forEach((value) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    select.append(option);
  });
}

async function loadMetadata() {
  try {
    const response = await fetch('/api/meta');
    if (!response.ok) throw new Error('Could not load property data. Refresh the page to try again.');
    metadata = await response.json();
    setOptions(stateSelect, metadata.states, 'Select a state');
    setOptions(typeSelect, metadata.types, 'Select a property type');
    stateFilter.replaceChildren(new Option('All available locations', 'all'));
    metadata.states.forEach((state) => stateFilter.add(new Option(state === 'Abuja' ? 'Abuja / FCT' : state, state)));
    document.getElementById('listing-count').textContent = Number(metadata.listingCount).toLocaleString('en-NG');
    const supported = metadata.supportedStates;
    const hasAbuja = metadata.states.includes('Abuja');
    document.getElementById('estimate-state-count').textContent = `${metadata.states.length - (hasAbuja ? 1 : 0)} states${hasAbuja ? ' + Abuja/FCT' : ''}`;
    document.getElementById('estimate-state-list').textContent = supported.join(' · ');
  } catch (error) {
    stateSelect.replaceChildren(new Option('Locations unavailable', ''));
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  }
}

stateSelect.addEventListener('change', () => {
  const state = stateSelect.value;
  const isSupported = Boolean(state && metadata && metadata.supportedStates.includes(state));
  townSelect.disabled = !isSupported;
  typeSelect.disabled = !isSupported;
  setOptions(townSelect, isSupported ? metadata.towns[state] : [], isSupported ? 'Select a town or area' : state ? 'Not enough local data yet' : 'Choose a state first');
  if (isSupported) {
    setOptions(typeSelect, metadata.types, 'Select a property type');
    errorBox.hidden = true;
  } else if (state && metadata) {
    const count = metadata.stateCounts[state] || 0;
    errorBox.textContent = `Moshelter has ${count} usable listings for ${state}; it needs at least ${metadata.minimumStateListings} to estimate a price responsibly. You can browse properties in every location represented in this dataset while more price data is collected.`;
    errorBox.hidden = false;
  } else {
    errorBox.hidden = true;
  }
});

function formatNaira(amount) {
  return '₦' + Math.round(amount).toLocaleString('en-NG');
}

function formatHomePrice(home) {
  const price = formatNaira(home.price);
  if (home.transaction_type !== 'rent') return `${price} · for sale`;
  return `${price} / ${home.rent_frequency === 'yearly' ? 'year' : 'month'}`;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  if (!metadata || !metadata.supportedStates.includes(stateSelect.value)) {
    if (metadata) stateSelect.dispatchEvent(new Event('change'));
    else { errorBox.textContent = 'Wait for the property data to finish loading, then try again.'; errorBox.hidden = false; }
    return;
  }
  if (!form.reportValidity()) return;
  const formData = new FormData(form);
  const payload = {
    state: formData.get('state'), town: formData.get('town'), title: formData.get('title'),
    bedrooms: Number(formData.get('bedrooms')), bathrooms: Number(formData.get('bathrooms')),
    toilets: Number(formData.get('toilets')), parking_space: Number(formData.get('parking_space'))
  };
  submitButton.disabled = true;
  submitButton.innerHTML = 'Finding similar listings <span aria-hidden="true">…</span>';
  resultStatus.textContent = 'COMPARING SIMILAR LISTINGS';
  try {
    const response = await fetch('/api/predict', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The estimate could not be prepared.');
    document.getElementById('price-value').textContent = formatNaira(result.estimate);
    document.getElementById('match-copy').textContent = 'Compared with ' + result.comparables + ' similar listings; ' + result.match + '.';
    document.getElementById('match-breakdown').textContent = result.sameTownAndTypeComparables + ' matched both your town and property type; ' + result.sameTownComparables + ' were in your town; ' + result.sameTypeComparables + ' were the same property type.';
    document.getElementById('range-value').textContent = formatNaira(result.rangeLow) + ' – ' + formatNaira(result.rangeHigh);
    emptyResult.hidden = true;
    priceResult.hidden = false;
    resultStatus.textContent = 'ESTIMATE READY';
    document.getElementById('result-card').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
    resultStatus.textContent = 'MORE DETAILS NEEDED';
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = 'Estimate asking price <span aria-hidden="true">→</span>';
  }
});

document.getElementById('edit-details').addEventListener('click', () => {
  document.getElementById('estimator').scrollIntoView({ behavior: 'smooth' });
  document.getElementById('state').focus({ preventScroll: true });
});

const homesGrid = document.getElementById('homes-grid');
const listingFilter = document.getElementById('listing-filter');
const stateFilter = document.getElementById('state-filter');
let availableHomes = [];
const homeDialog = document.getElementById('home-dialog');
const tourForm = document.getElementById('tour-form');

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function homeFeatures(home) {
  const features = [];
  if (home.bedrooms) features.push(`${home.bedrooms} bed`);
  if (home.bathrooms) features.push(`${home.bathrooms} bath`);
  if (home.toilets) features.push(`${home.toilets} toilet`);
  if (home.parking_space) features.push(`${home.parking_space} parking`);
  return features.length ? features.join(' · ') : 'Details available on request';
}

function renderHomeCard(home) {
  const card = makeElement('article', 'home-card');
  const photo = makeElement('div', 'home-card-photo');
  if (home.image_url) {
    const image = makeElement('img', '');
    image.src = home.image_url;
    image.alt = `Photo of ${home.title}`;
    image.loading = 'lazy';
    image.addEventListener('error', () => {
      image.remove();
      photo.append(makeElement('span', 'home-photo-icon', '⌂'));
    }, { once: true });
    photo.append(image);
  } else {
    photo.append(makeElement('span', 'home-photo-icon', '⌂'));
  }
  photo.append(makeElement('span', 'home-availability', home.transaction_type === 'rent' ? 'For rent' : 'For sale'));
  const details = makeElement('div', 'home-card-details');
  details.append(makeElement('p', 'home-card-location', `${home.town}, ${home.state}`));
  details.append(makeElement('h3', '', home.title));
  details.append(makeElement('p', 'home-card-type', home.property_type));
  details.append(makeElement('p', 'home-card-price', formatHomePrice(home)));
  details.append(makeElement('p', 'home-card-features', homeFeatures(home)));
  const action = makeElement('button', 'button button-primary home-card-action', 'View details & request a viewing →');
  action.type = 'button';
  action.addEventListener('click', () => openHomeDialog(home));
  details.append(action);
  card.append(photo, details);
  return card;
}

function renderHomes(homes) {
  homesGrid.replaceChildren();
  if (!homes.length) {
    const empty = makeElement('div', 'homes-empty');
    empty.append(makeElement('span', 'homes-empty-icon', '⌂'));
    empty.append(makeElement('h3', '', 'No listings match this filter yet.'));
    empty.append(makeElement('p', '', 'Try another filter, or check back when Moshelter adds more available homes, rooms, studios and shops.'));
    homesGrid.append(empty);
    return;
  }
  homes.forEach((home) => homesGrid.append(renderHomeCard(home)));
}

function filterListings() {
  const transaction = listingFilter.value;
  const state = stateFilter.value;
  renderHomes(availableHomes.filter((home) => {
    const matchesTransaction = transaction === 'all' || home.transaction_type === transaction;
    const matchesState = state === 'all' || (state === 'FCT'
      ? ['Abuja','Federal Capital Territory'].includes(home.state)
      : home.state === state);
    return matchesTransaction && matchesState;
  }));
}

async function loadAvailableHomes() {
  try {
    const response = await fetch('/api/homes', { cache: 'no-store' });
    if (!response.ok) throw new Error('Available homes could not be loaded. Please refresh the page.');
    const result = await response.json();
    availableHomes = result.homes || [];
    filterListings();
  } catch (error) {
    homesGrid.replaceChildren(makeElement('p', 'homes-loading', error.message));
  }
}

function openHomeDialog(home) {
  const photo = document.getElementById('home-dialog-photo');
  photo.replaceChildren();
  if (home.image_url) {
    const image = makeElement('img', '');
    image.src = home.image_url;
    image.alt = `Photo of ${home.title}`;
    image.addEventListener('error', () => {
      image.remove();
      photo.append(makeElement('span', '', '⌂'));
    }, { once: true });
    photo.append(image);
  } else {
    photo.append(makeElement('span', '', '⌂'));
  }
  document.getElementById('home-dialog-location').textContent = `${home.town}, ${home.state} · ${home.property_type}`;
  document.getElementById('home-dialog-title').textContent = home.title;
  document.getElementById('home-dialog-price').textContent = formatHomePrice(home);
  const featureParts = [];
  if (home.bedrooms) featureParts.push(`${home.bedrooms} bedrooms`);
  if (home.bathrooms) featureParts.push(`${home.bathrooms} bathrooms`);
  if (home.toilets) featureParts.push(`${home.toilets} toilets`);
  if (home.parking_space) featureParts.push(`${home.parking_space} parking spaces`);
  document.getElementById('home-dialog-meta').textContent = featureParts.join(' · ');
  document.getElementById('home-dialog-description').textContent = home.description;
  tourForm.elements.home_id.value = home.id;
  document.getElementById('tour-form-status').textContent = '';
  const localMinimum = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  tourForm.elements.preferred_at.min = localMinimum;
  if (!homeDialog.open) homeDialog.showModal();
}

document.getElementById('home-dialog-close').addEventListener('click', () => homeDialog.close());

tourForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = document.getElementById('tour-form-status');
  const button = tourForm.querySelector('button[type="submit"]');
  button.disabled = true;
  status.textContent = 'Sending your tour request…';
  const fields = new FormData(tourForm);
  const payload = Object.fromEntries(fields.entries());
  payload.home_id = Number(payload.home_id);
  try {
    const response = await fetch('/api/tours', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Your tour request could not be sent.');
    status.textContent = result.message;
    const homeId = tourForm.elements.home_id.value;
    tourForm.reset();
    tourForm.elements.home_id.value = homeId;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

listingFilter.addEventListener('change', () => {
  filterListings();
});
stateFilter.addEventListener('change', filterListings);

loadMetadata();
loadAvailableHomes();
