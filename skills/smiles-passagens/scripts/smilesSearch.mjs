import { calendarEndpoint, httpGetJson } from "./client.mjs";

const validationError = (message) => Object.assign(new Error(message), { code: "VALIDATION" });

const toISO = (raw) => {
  if (typeof raw !== "string" || !/^\d{2}\/\d{2}\/\d{4}$/.test(raw)) {
    throw validationError("Dates must be DD/MM/YYYY");
  }
  const [day, month, year] = raw.split("/").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (year < 1000 || date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    throw validationError(`Invalid calendar date: ${raw}`);
  }
  return date.toISOString().slice(0, 10);
};

const windowStart = (raw) => {
  const [year, month] = toISO(raw).split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, 0)).toISOString().slice(0, 10);
};

const windowEnd = (raw) => {
  const [year, month] = toISO(raw).split("-").map(Number);
  return new Date(Date.UTC(year, month, 1)).toISOString().slice(0, 10);
};

const priceForDate = (days, isoDate) => {
  for (const day of days) {
    if (day?.fare?.type !== "SMILES_CLUB") continue;
    if (day.date === isoDate) return typeof day.miles === "number" ? day.miles : null;
  }
  return null;
};

/** Three cheapest distinct SMILES_CLUB prices → { miles: [isoDates] } */
const cheapestDays = (days) => {
  const prices = [];
  for (const day of days) {
    if (day?.fare?.type !== "SMILES_CLUB") continue;
    if (typeof day.miles !== "number") continue;
    if (!prices.includes(day.miles)) prices.push(day.miles);
  }
  prices.sort((a, b) => a - b);
  const top = prices.slice(0, 3);
  const byPrice = {};
  for (const day of days) {
    if (day?.fare?.type !== "SMILES_CLUB") continue;
    if (top.includes(day.miles)) {
      if (!byPrice[day.miles]) byPrice[day.miles] = [];
      byPrice[day.miles].push(day.date);
    }
  }
  return byPrice;
};

/**
 * @param {object} opts
 * @param {string} opts.origin IATA
 * @param {string} opts.destination IATA
 * @param {string} opts.departureRaw DD/MM/YYYY
 * @param {string} opts.returnRaw DD/MM/YYYY
 * @param {number|string} opts.adults
 * @param {(url: string) => Promise<any>} [opts.httpGet]
 */
export async function searchSmiles({
  origin,
  destination,
  departureRaw,
  returnRaw,
  adults,
  httpGet = httpGetJson,
}) {
  const departureDate = toISO(departureRaw);
  const returnDate = toISO(returnRaw);
  if (returnDate < departureDate) throw validationError("Return date must be on or after departure");
  if (!Number.isInteger(Number(adults)) || Number(adults) < 1 || Number(adults) > 9) {
    throw validationError("--adults must be an integer between 1 and 9");
  }
  const params = new URLSearchParams({
    memberNumber: "",
    originAirportCode: origin,
    destinationAirportCode: destination,
    departureDate,
    adults: String(adults),
    children: "0",
    infants: "0",
    forceCongener: "false",
    cabin: "ECONOMIC",
    bestFare: "true",
    returnDate,
    startDate: windowStart(departureRaw),
    endDate: windowEnd(departureRaw),
    startDate2: windowStart(returnRaw),
    endDate2: windowEnd(returnRaw),
  });

  const url = `${calendarEndpoint()}?${params.toString()}`;
  const data = await httpGet(url);

  if (
    !data?.hasCalendar ||
    !data?.calendarSegmentList?.[0] ||
    !data?.calendarSegmentList?.[1]
  ) {
    return null;
  }

  const going = data.calendarSegmentList[0].calendarDayList || [];
  const back = data.calendarSegmentList[1].calendarDayList || [];

  return {
    origin,
    destination,
    adults: Number(adults),
    departure: { date: departureDate, miles: priceForDate(going, departureDate) },
    return: { date: returnDate, miles: priceForDate(back, returnDate) },
    cheapestDeparture: cheapestDays(going),
    cheapestReturn: cheapestDays(back),
  };
}

export { toISO, windowStart, windowEnd };
