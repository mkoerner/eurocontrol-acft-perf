from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, Dict, List, Any, Union
import argparse
import csv
import logging
import os
import pathlib
import pickle
import random
import re
import time
import requests as rq
import bs4 as bs


__author__ = "Mathias Koerner"
__copyright__ = "(c) 2022, Mathias Koerner"
__license__ = "MIT (https://github.com/mkoerner/eurocontrol-acft-perf/LICENSE)"


URL = "https://contentzone.eurocontrol.int/aircraftperformance/"


LOGLEVEL = LOGLEVEL = os.environ.get("LOGLEVEL", "INFO").upper()
logging.basicConfig(level=LOGLEVEL)


@dataclass
class PageState:
    """ASP.NET state"""

    view_state: str = ""
    view_state_generator: str = ""
    event_validation: str = ""

    def data(self) -> Dict[str, str]:
        res = {}
        res["__VIEWSTATE"] = self.view_state
        res["__VIEWSTATEGENERATOR"] = self.view_state_generator
        res["__EVENTVALIDATION"] = self.event_validation
        return res

    @staticmethod
    def extract(soup: bs.BeautifulSoup) -> PageState:
        """Request for page"""
        return PageState(
            view_state=soup.find("input", attrs={"name": "__VIEWSTATE"})["value"],  # type:ignore
            view_state_generator=soup.find("input", attrs={"name": "__VIEWSTATEGENERATOR"})["value"],  # type:ignore
            event_validation=soup.find("input", attrs={"name": "__EVENTVALIDATION"})["value"],  # type:ignore
        )


@dataclass
class PageEvent:
    event_target: str = "ctl00$MainContent$wsBasicSearchGridView"
    event_argument: str = ""

    @staticmethod
    def page(i: int):
        return PageEvent(event_argument=f"Page${i}")

    def data(self) -> Dict[str, str]:
        res = {}
        res["__EVENTTARGET"] = self.event_target
        res["__EVENTARGUMENT"] = self.event_argument
        return res


def retrieve_front() -> Tuple[bs.BeautifulSoup, PageState]:
    """Retrieve front page to start scrape"""
    raw = rq.get(URL).text
    soup = bs.BeautifulSoup(raw, "html.parser")
    return soup, PageState.extract(soup)


def retrieve_page(evt: PageEvent, state: PageState) -> Tuple[bs.BeautifulSoup, PageState]:
    """Retrieve given page using previous state"""
    raw = rq.post(URL, data=evt.data() | state.data()).text
    soup = bs.BeautifulSoup(raw, "html.parser")
    return soup, PageState.extract(soup)


def scrape_designators(soup: bs.BeautifulSoup) -> List[str]:
    """Function to scrape the designators"""
    # Find ap-list-row and ap-list-row-alternate
    res = [e.text.strip() for e in soup.select("tr[class^=ap-list-row] h3 a")]
    logging.info(f"Found designators {res}")
    return res


def max_page_no(soup: bs.BeautifulSoup) -> int:
    """Return maximum page number found in document"""
    ts = {e.text.strip() for e in soup.select("tr[class=ap-list-pager] a")}
    ts = ts.union({e.text.strip() for e in soup.select("tr[class=ap-list-pager] span")})
    last = [e.text.strip() for e in soup.select("tr[class=ap-list-pager] a")][-1]
    n = max({int(e) for e in ts if e != "..."})
    n = n + 1 if last == "..." else n
    logging.debug(f"Maximum page guessed is {n}")
    return n


def retrieve_icao(icao: str) -> str:
    """Retrieve detail page for icao code"""
    return rq.get(f"{URL}details.aspx?ICAO={icao}").text


NUMBER_PATTERN: re.Pattern[str] = re.compile(r"[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?")


def strip_units(value: str) -> float:
    """Strip units from float with regular expression"""
    values = NUMBER_PATTERN.findall(value)
    return float(values[0][0])


def scrape_icao(raw: str) -> Dict[str, Union[str, float]]:
    """Scrape results from details page"""
    soup = bs.BeautifulSoup(raw, "html.parser")
    result: Dict[str, Union[str, float]] = {}
    result["ICAO"] = soup.select("span[id=MainContent_wsICAOLabel]")[0].text
    result["AircraftName"] = soup.select("span[id=MainContent_wsAcftNameLabel]")[0].text
    result["Manufacturer"] = soup.select("span[id=MainContent_wsManufacturerLabel]")[0].text
    result["WingSpan_m"] = strip_units(soup.select("span[id=MainContent_wsLabelWingSpan]")[0].text)
    result["Lenght_m"] = strip_units(soup.select("span[id=MainContent_wsLabelLength]")[0].text)
    result["Height_m"] = strip_units(soup.select("span[id=MainContent_wsLabelHeight]")[0].text)
    result["Cruise_kt"] = strip_units(soup.select("span[datagraph=cruiseTAS]")[0].text)
    result["CruiseCeiling_FL"] = int(soup.select("span[datagraph=cruiseCeiling]")[0].text)
    return result


def wait():
    """Don't spam the server"""
    time.sleep(random.randint(3, 5))


def retrieve_designators() -> List[str]:
    """Retrieve all designators"""
    designators: List[str] = []
    n = 1
    logging.info(f"Requesting page number {n}")
    page, state = retrieve_front()
    max_page = max_page_no(page)
    designators += scrape_designators(page)
    wait()
    while n < max_page:
        n += 1
        logging.info(f"Requesting page number {n}")
        page, state = retrieve_page(PageEvent.page(n), state)
        max_page = max(max_page, max_page_no(page))
        designators += scrape_designators(page)
        wait()
    return designators


DetailedResult = Tuple[List[Dict[str, Any]], Dict[str, str]]


def retrieve_details(ds: List[str]) -> DetailedResult:
    """Retrieve all details"""
    logging.info(f"Getting details for {len(ds)} aircrafts")
    details = []
    pages = {}
    for d in ds:
        logging.info(f"Processing {d}")
        pages[d] = retrieve_icao(d)
        icao = scrape_icao(pages[d])
        details.append(icao)
        wait()
    return details, pages


def scrape_details(ds: Dict[str, str]) -> List[Dict[str, Any]]:
    """Only scrape details"""
    logging.info(f"Scraping details for {len(ds)} aircrafts")
    details = []
    for d, page in ds.items():
        logging.info(f"Processing {d}")
        icao = scrape_icao(page)
        details.append(icao)
    return details


KEYS = [
    "ICAO",
    "AircraftName",
    "Manufacturer",
    "WingSpan_m",
    "Lenght_m",
    "Height_m",
    "Cruise_kt",
    "CruiseCeiling_FL",
]


def main(args: argparse.Namespace):
    if args.rawfile is not None and pathlib.Path(args.rawfile).exists():
        logging.info(f"Scraping information from pickle {args.rawfile}")
        with open(args.rawfile, "rb") as f:
            pages = pickle.load(f)
            details = scrape_details(pages)
    else:
        logging.info("Retrieveing and scraping information from server")
        designators = retrieve_designators()
        details, pages = retrieve_details(designators)
    if args.rawfile is not None and not pathlib.Path(args.rawfile).exists():
        logging.info(f"Pickling raw data to {args.rawfile}")
        with open(args.rawfile, "wb") as f:
            pickle.dump(pages, f)
    logging.info(f"Saving result CSV to {args.output}")
    with open(args.output, "w") as f:
        writer = csv.DictWriter(f, KEYS)
        writer.writeheader()
        writer.writerows(details)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"Scrape aircraft details from {URL}")
    parser.add_argument("output", type=str, help="Output file for details")
    parser.add_argument("--rawfile", type=str, help="Output/input raw file to bypass scrape")
    args = parser.parse_args()
    main(args)
