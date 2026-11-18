const loginCard = document.getElementById('login-card');
const workspace = document.getElementById('admin-workspace');
const loginForm = document.getElementById('login-form');
const homeForm = document.getElementById('home-form');
const notice = document.getElementById('admin-notice');
const homesList = document.getElementById('admin-homes');
const toursList = document.getElementById('admin-tours');
const saveButton = document.getElementById('save-home-button');

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function naira(value) { return '₦' + Number(value).toLocaleString('en-NG'); }
function listingPrice(home) { return naira(home.price) + (home.transaction_type === 'rent' ? ` / ${home.rent_frequency === 'yearly' ? 'year' : 'month'}` : ''); }
function showNotice(message, isError = false) {
  notice.hidden = !message;
  notice.textContent = message || '';
  notice.classList.toggle('is-error', isError);
}
async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || 'The request could not be completed.');
  return result;
}

const stateSelect = homeForm.elements.state;
stateSelect.replaceChildren(new Option('Loading dataset locations…', ''));
api('/api/meta').then((metadata) => {
  stateSelect.replaceChildren(new Option('Choose a state or Abuja location', ''));
  metadata.states.forEach((state) => stateSelect.add(new Option(state, state)));
}).catch((error) => showNotice(error.message, true));
const transactionSelect = homeForm.elements.transaction_type;
const rentFrequencyField = document.getElementById('rent-frequency-field');
const priceLabel = document.getElementById('price-label');
function updateTransactionFields() {
  const isRent = transactionSelect.value === 'rent';
  rentFrequencyField.hidden = !isRent;
  priceLabel.textContent = isRent ? 'Rent amount (₦)' : 'Asking price (₦)';
}
transactionSelect.addEventListener('change', updateTransactionFields);

function showWorkspace(authenticated) {
  loginCard.hidden = authenticated;
  workspace.hidden = !authenticated;
  document.getElementById('logout-button').hidden = !authenticated;
  document.getElementById('session-label').textContent = authenticated ? 'Signed in as administrator' : 'Administrator access';
}

async function loadAdminData() {
  try {
    const [homes, tours] = await Promise.all([api('/api/admin/homes'), api('/api/admin/tours')]);
    document.getElementById('listing-count').textContent = homes.homes.length.toLocaleString('en-NG');
    document.getElementById('tour-count').textContent = tours.tours.length.toLocaleString('en-NG');
    renderHomes(homes.homes);
    renderTours(tours.tours);
  } catch (error) {
    showNotice(error.message, true);
  }
}

async function checkSession() {
  try {
    const session = await api('/api/admin/status');
    document.getElementById('setup-help').hidden = session.configured;
    loginForm.querySelector('button').disabled = !session.configured;
    showWorkspace(session.authenticated);
    if (session.authenticated) await loadAdminData();
  } catch (error) {
    showNotice(error.message, true);
  }
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  showNotice('');
  const button = loginForm.querySelector('button');
  button.disabled = true;
  try {
    await api('/api/admin/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({password: loginForm.elements.password.value}) });
    loginForm.reset();
    showWorkspace(true);
    await loadAdminData();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    button.disabled = !document.getElementById('setup-help').hidden;
  }
});

document.getElementById('logout-button').addEventListener('click', async () => {
  try { await api('/api/admin/logout', {method:'POST'}); } catch { /* A closed session is already signed out. */ }
  showWorkspace(false);
  showNotice('You have signed out.');
  await checkSession();
});
document.getElementById('refresh-button').addEventListener('click', loadAdminData);
document.getElementById('cancel-edit-button').addEventListener('click', resetHomeForm);

function resetHomeForm() {
  homeForm.reset();
  homeForm.elements.home_id.value = '';
  homeForm.elements.status.value = 'available';
  homeForm.elements.transaction_type.value = 'sale';
  homeForm.elements.rent_frequency.value = 'monthly';
  updateTransactionFields();
  homeForm.elements.bedrooms.value = 3;
  homeForm.elements.bathrooms.value = 2;
  homeForm.elements.toilets.value = 2;
  homeForm.elements.parking_space.value = 1;
  document.getElementById('editor-heading').textContent = 'Add a listing';
  saveButton.textContent = 'Publish listing';
  document.getElementById('cancel-edit-button').hidden = true;
  document.getElementById('home-form-message').textContent = '';
  document.getElementById('home-form-message').classList.remove('is-error');
}

homeForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = document.getElementById('home-form-message');
  message.textContent = 'Saving listing…';
  saveButton.disabled = true;
  const data = new FormData(homeForm);
  const payload = Object.fromEntries(data.entries());
  ['price','bedrooms','bathrooms','toilets','parking_space'].forEach((field) => { payload[field] = Number(payload[field]); });
  const id = payload.home_id;
  delete payload.home_id;
  try {
    await api(id ? `/api/admin/homes/${id}` : '/api/admin/homes', {
      method: id ? 'PUT' : 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
    const successMessage = id ? 'Listing updated.' : 'Listing published and visible to visitors.';
    message.textContent = successMessage;
    message.classList.remove('is-error');
    resetHomeForm();
    showNotice(successMessage);
    await loadAdminData();
  } catch (error) {
    message.textContent = error.message;
    message.classList.add('is-error');
  } finally {
    saveButton.disabled = false;
  }
});

function renderHomes(homes) {
  homesList.replaceChildren();
  if (!homes.length) {
    homesList.append(el('p','empty-message','No property listings yet. Add your first home, room, studio, or shop using the form.'));
    return;
  }
  homes.forEach((home) => {
    const entry = el('article','admin-entry');
    const top = el('div','entry-top');
    const titleBox = el('div','');
    titleBox.append(el('h3','',home.title));
    titleBox.append(el('p','entry-subtitle',`${home.town}, ${home.state} · ${home.property_type}`));
    top.append(titleBox,el('span',`entry-status ${home.status === 'unavailable' ? 'unavailable' : ''}`,home.status));
    entry.append(top,el('p','entry-price',listingPrice(home)));
    entry.append(el('p','entry-subtitle',home.transaction_type === 'rent' ? 'FOR RENT' : 'FOR SALE'));
    entry.append(el('p','entry-meta',`${home.bedrooms} beds · ${home.bathrooms} baths · ${home.parking_space} parking`));
    const actions = el('div','entry-actions');
    const edit = el('button','quiet-button','Edit listing');
    edit.type = 'button';
    edit.addEventListener('click', () => editHome(home));
    const availability = el('button','quiet-button',home.status === 'available' ? 'Mark unavailable' : 'Make available');
    availability.type = 'button';
    availability.addEventListener('click', () => changeAvailability(home));
    actions.append(edit,availability);
    entry.append(actions);
    homesList.append(entry);
  });
}

function editHome(home) {
  ['title','state','town','property_type','transaction_type','rent_frequency','price','bedrooms','bathrooms','toilets','parking_space','image_url','description','status'].forEach((field) => { homeForm.elements[field].value = home[field]; });
  updateTransactionFields();
  homeForm.elements.home_id.value = home.id;
  document.getElementById('editor-heading').textContent = 'Edit a listing';
  saveButton.textContent = 'Save changes';
  document.getElementById('cancel-edit-button').hidden = false;
  document.getElementById('home-form-message').textContent = '';
  homeForm.scrollIntoView({behavior:'smooth',block:'start'});
}

async function changeAvailability(home) {
  const payload = {...home, status: home.status === 'available' ? 'unavailable' : 'available'};
  delete payload.id;
  try {
    await api(`/api/admin/homes/${home.id}`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    showNotice(home.status === 'available' ? 'Listing marked unavailable.' : 'Listing is available to visitors again.');
    await loadAdminData();
  } catch (error) { showNotice(error.message,true); }
}

const tourStatuses = [['requested','Requested'],['confirmed','Confirmed'],['completed','Completed'],['cancelled','Cancelled']];
function renderTours(tours) {
  toursList.replaceChildren();
  if (!tours.length) {
    toursList.append(el('p','empty-message','No viewing requests yet. New visitor requests will appear here.'));
    return;
  }
  tours.forEach((tour) => {
    const entry = el('article','tour-entry');
    const grid = el('div','tour-grid');
    const details = el('div','');
    details.append(el('h3','',tour.home_title));
    details.append(el('p','',`${tour.home_town}, ${tour.home_state} · ${naira(tour.home_price)}${tour.home_transaction_type === 'rent' ? ` / ${tour.home_rent_frequency === 'yearly' ? 'year' : 'month'}` : ''}`));
    details.append(el('p','',`${tour.name} · ${tour.tour_type === 'virtual' ? 'Virtual tour' : 'In-person tour'}`));
    const preferredDate = new Date(tour.preferred_at);
    details.append(el('p','',`Preferred: ${Number.isNaN(preferredDate.valueOf()) ? tour.preferred_at : preferredDate.toLocaleString('en-NG')}`));
    const contact = el('p','');
    const email = el('a','','Email visitor'); email.href = `mailto:${tour.email}`;
    const phone = el('a','','Call visitor'); phone.href = `tel:${tour.phone}`;
    contact.append(email,document.createTextNode(' · '),phone);
    details.append(contact);
    if (tour.note) details.append(el('p','','Note: ' + tour.note));
    const status = document.createElement('select');
    status.setAttribute('aria-label',`Status for tour request ${tour.id}`);
    tourStatuses.forEach(([value,label]) => status.add(new Option(label,value)));
    status.value = tour.status;
    status.addEventListener('change',async () => {
      status.disabled=true;
      try { await api(`/api/admin/tours/${tour.id}/status`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:status.value})}); showNotice('Tour request status updated.'); }
      catch(error){showNotice(error.message,true);status.value=tour.status;}
      finally{status.disabled=false;}
    });
    grid.append(details,status);
    entry.append(grid);
    toursList.append(entry);
  });
}

checkSession();
