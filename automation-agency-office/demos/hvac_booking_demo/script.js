const form = document.getElementById('bookingForm');
const workflowItems = [...document.querySelectorAll('#workflowList li')];
const resultPanel = document.getElementById('resultPanel');
const resultEmpty = document.querySelector('.result-empty');
const confirmationCard = document.getElementById('confirmationCard');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function resetWorkflow() {
  workflowItems.forEach((item) => {
    item.classList.remove('active', 'done');
  });
}

async function runWorkflow() {
  for (const item of workflowItems) {
    item.classList.add('active');
    await sleep(550);
    item.classList.remove('active');
    item.classList.add('done');
  }
}

function fmtDate(rawDate) {
  if (!rawDate) return 'Not provided';
  const d = new Date(rawDate + 'T00:00:00');
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();

  if (!form.reportValidity()) {
    return;
  }

  const fullName = document.getElementById('fullName').value.trim();
  const phone = document.getElementById('phone').value.trim();
  const serviceType = document.getElementById('serviceType').value;
  const preferredDate = document.getElementById('preferredDate').value;
  const issue = document.getElementById('issue').value.trim();

  resetWorkflow();
  confirmationCard.classList.add('hidden');
  resultEmpty.textContent = 'Running automation...';

  await runWorkflow();

  resultEmpty.textContent = 'Automation completed successfully.';
  confirmationCard.innerHTML = `
    <h3>Appointment Confirmed</h3>
    <p><strong>Customer:</strong> ${fullName}</p>
    <p><strong>Phone:</strong> ${phone}</p>
    <p><strong>Service:</strong> ${serviceType}</p>
    <p><strong>Scheduled Date:</strong> ${fmtDate(preferredDate)}</p>
    <p><strong>Issue:</strong> ${issue}</p>
    <p><strong>Status:</strong> Lead captured · Confirmation generated · Reminder queued</p>
  `;
  confirmationCard.classList.remove('hidden');
  resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
