import test from 'node:test';
import assert from 'node:assert/strict';
import { toISO, windowStart, windowEnd, searchSmiles } from '../scripts/smilesSearch.mjs';
const query = { origin: 'GYN', destination: 'REC', departureRaw: '15/03/2027', returnRaw: '22/03/2027', adults: 1 };
test('calendar boundaries handle leap years and year rollover', () => {
  assert.equal(windowStart('15/03/2027'), '2027-02-28');
  assert.equal(windowStart('15/03/2028'), '2028-02-29');
  assert.equal(windowStart('15/01/2027'), '2026-12-31');
  assert.equal(windowEnd('15/12/2027'), '2028-01-01');
  assert.equal(toISO('29/02/2028'), '2028-02-29');
  for (const date of ['29/02/2027', '31/04/2027', '00/01/2027', '15/13/2027', '2027-03-15']) assert.throws(() => toISO(date), { code: 'VALIDATION' });
});
test('bad dates, ordering and passenger counts never call transport', async () => {
  for (const fields of [{ returnRaw: '14/03/2027' }, { adults: 1.5 }, { adults: 10 }, { adults: 0 }, { departureRaw: '31/02/2027' }]) {
    await assert.rejects(searchSmiles({ ...query, ...fields, httpGet: () => assert.fail('must not request') }), { code: 'VALIDATION' });
  }
});
test('keeps club fares and three distinct prices; missing requested day remains null', async () => {
  const days = [9, 9, 10, 11, 12].map((miles, i) => ({ date: `2027-03-${15 + i}`, miles, fare: { type: 'SMILES_CLUB' } }));
  days.push({ date: '2027-03-15', miles: 1, fare: { type: 'OTHER' } });
  const result = await searchSmiles({ ...query, httpGet: async url => {
    assert.equal(new URL(url).searchParams.get('startDate'), '2027-02-28');
    return { hasCalendar: true, calendarSegmentList: [{ calendarDayList: days }, { calendarDayList: [] }] };
  }});
  assert.equal(result.departure.miles, 9);
  assert.equal(result.return.miles, null);
  assert.deepEqual(Object.keys(result.cheapestDeparture), ['9', '10', '11']);
  assert.equal(result.cheapestDeparture[9].length, 2);
});
test('empty calendars and transport errors remain distinct', async () => {
  assert.equal(await searchSmiles({ ...query, httpGet: async () => ({ hasCalendar: false }) }), null);
  await assert.rejects(searchSmiles({ ...query, httpGet: async () => { throw new Error('HTTP 503'); } }), /503/);
});
