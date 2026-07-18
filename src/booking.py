"""Core reservation and booking analysis functionality for restaurants.

Includes Places API searches, website scraping, and reservation options detection.
"""

import os
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx

_PLACES_FIELDS = [
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.reservable"
]
_PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"


def parse_date(date_str: str) -> str:
    """Parses standard or relative date strings (today, tomorrow) to YYYY-MM-DD."""
    date_str = date_str.lower().strip()
    now = datetime.now()
    if date_str == "today":
        return now.strftime("%Y-%m-%d")
    elif date_str == "tomorrow":
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Try parsing YYYY-MM-DD
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return date_str


def search_restaurant(query: str, api_key: str) -> dict[str, Any] | None:
    """Searches for a restaurant using Google Places API (New)."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ",".join(_PLACES_FIELDS),
    }
    payload = {
        "textQuery": query,
        "includedType": "restaurant",
        "maxResultCount": 1
    }
    
    try:
        response = httpx.post(_PLACES_ENDPOINT, headers=headers, json=payload, timeout=10.0)
        if response.status_code != 200:
            return None
        
        data = response.json()
        places = data.get("places", [])
        if not places:
            payload.pop("includedType", None)
            response = httpx.post(_PLACES_ENDPOINT, headers=headers, json=payload, timeout=10.0)
            if response.status_code == 200:
                places = response.json().get("places", [])
        
        return places[0] if places else None
    except Exception:
        return None


def extract_emails(html: str) -> list[str]:
    """Finds all booking/reservation-related emails in the HTML string."""
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, html)
    
    unique_emails = sorted(list(set(emails)))
    booking_emails = [e for e in unique_emails if any(k in e.lower() for k in ["book", "reserv", "info", "contact"])]
    if booking_emails:
        return booking_emails
    return unique_emails[:3]


def extract_zenchef_id(html: str, links: list[str]) -> str | None:
    """Scans HTML and links to find Zenchef restaurant ID or alias."""
    data_res_match = re.search(r'data-restaurant=["\'](\d+)["\']', html)
    if data_res_match:
        return data_res_match.group(1)
        
    js_res_match = re.search(r'(?:restaurantId|restaurant)\s*:\s*["\'](\d+)["\']', html)
    if js_res_match:
        return js_res_match.group(1)
        
    zenchef_patterns = [
        r'booking\.zenchef\.com/consumers/init/index/restaurant/([a-zA-Z0-9_-]+)',
        r'link\.zenchef\.com/r/([a-zA-Z0-9_-]+)',
        r'mymenu\.zenchef\.com/r/([a-zA-Z0-9_-]+)',
        r'rid=(\d+)'
    ]
    for link in links:
        for pattern in zenchef_patterns:
            match = re.search(pattern, link)
            if match:
                return match.group(1)
                
    return None


def scrape_website(website_url: str) -> dict[str, Any]:
    """Scrapes the restaurant website to find booking links and details."""
    result = {
        "status": "Not Checked",
        "zenchef_id": None,
        "booking_links": {},
        "emails": [],
        "generic_booking_paths": []
    }
    
    if not website_url:
        result["status"] = "No Website Provided"
        return result

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = httpx.get(website_url, headers=headers, timeout=8.0, follow_redirects=True)
        result["status"] = f"Fetched ({response.status_code})"
        
        if response.status_code != 200:
            return result
            
        html = response.text
        
        href_links = re.findall(r'href=["\'](https?://[^"\']+|/[^"\']+)["\']', html, re.IGNORECASE)
        parsed_url = urlparse(website_url)
        base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        absolute_links = []
        for link in href_links:
            if link.startswith("/"):
                absolute_links.append(base_domain + link)
            else:
                absolute_links.append(link)
                
        zenchef_id = extract_zenchef_id(html, absolute_links)
        if zenchef_id:
            result["zenchef_id"] = zenchef_id
            
        platforms = {
            "zenchef": ["zenchef.com"],
            "thefork": ["thefork.com", "lafourchette.com", "thefork.fr", "thefork.it", "thefork.es"],
            "opentable": ["opentable.com", "opentable.co.uk"],
            "resy": ["resy.com"],
            "sevenrooms": ["sevenrooms.com"]
        }
        
        for link in absolute_links:
            for platform, domains in platforms.items():
                if any(domain in link.lower() for domain in domains):
                    result["booking_links"][platform] = link
            
            if any(k in link.lower() for k in ["/book", "/reserve", "/booking", "/reservation"]):
                if link not in result["generic_booking_paths"] and link != website_url:
                    result["generic_booking_paths"].append(link)
                    
        result["emails"] = extract_emails(html)
        
    except Exception as e:
        result["status"] = f"Failed to Fetch: {str(e)}"
        
    return result


def investigate_restaurant_booking(
    restaurant_query: str,
    date_str: str = "today",
    time_start: str = "19:00",
    time_end: str = "21:00",
    pax: int = 2,
    api_key: str | None = None
) -> dict[str, Any]:
    """Performs full search and scraping analysis for a restaurant booking."""
    if not api_key:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
        if not api_key:
            raise ValueError("No Google Places API key found in parameters or environment.")
            
    target_date = parse_date(date_str)
    
    place = search_restaurant(restaurant_query, api_key)
    if not place:
        return {
            "error": f"Restaurant '{restaurant_query}' not found via Google Places API."
        }
        
    name = place.get("displayName", {}).get("text", "Unknown Name")
    address = place.get("formattedAddress", "Unknown Address")
    phone = place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber")
    website = place.get("websiteUri")
    google_maps_url = place.get("googleMapsUri")
    reservable = place.get("reservable")
    
    scraping_results = scrape_website(website)
    
    booking_options = []
    
    # 1. Zenchef
    zenchef_id = scraping_results.get("zenchef_id")
    zenchef_link = scraping_results.get("booking_links", {}).get("zenchef")
    
    if zenchef_id or zenchef_link:
        option = {
            "type": "zenchef",
            "name": "Zenchef Online Booking",
            "recommended": True
        }
        if zenchef_id:
            option["restaurant_id"] = zenchef_id
            option["booking_url"] = f"https://bookings.zenchef.com/results?rid={zenchef_id}&day={target_date}&slot={time_start}&pax={pax}"
        elif zenchef_link:
            option["booking_url"] = zenchef_link
        booking_options.append(option)
        
    # 2. Other platforms
    other_platforms = {
        "thefork": "TheFork",
        "opentable": "OpenTable",
        "resy": "Resy",
        "sevenrooms": "SevenRooms"
    }
    for key, label in other_platforms.items():
        link = scraping_results.get("booking_links", {}).get(key)
        if link:
            booking_options.append({
                "type": key,
                "name": f"{label} Booking Page",
                "booking_url": link
            })
            
    # 3. Email
    emails = scraping_results.get("emails", [])
    if emails:
        booking_options.append({
            "type": "email",
            "name": "Email Reservation",
            "emails": emails,
            "note": "Email reservations may require manual confirmation."
        })
        
    # 4. Custom Website Pages
    generic_paths = scraping_results.get("generic_booking_paths", [])
    if generic_paths:
        booking_options.append({
            "type": "website_page",
            "name": "Custom Restaurant Booking Page",
            "urls": generic_paths[:3]
        })
        
    # 5. Phone Option
    if phone:
        booking_options.append({
            "type": "phone",
            "name": "Phone Reservation",
            "phone_number": phone,
            "status": "Ready for voice agent dial"
        })
        
    # 6. Fallback Place Page
    if google_maps_url:
        booking_options.append({
            "type": "google_maps",
            "name": "Google Maps Reservation option / Place Page",
            "booking_url": google_maps_url
        })
        
    return {
        "restaurant_details": {
            "name": name,
            "address": address,
            "phone": phone,
            "website": website,
            "google_maps_url": google_maps_url,
            "reservable": reservable
        },
        "search_parameters": {
            "target_date": target_date,
            "time_start": time_start,
            "time_end": time_end,
            "pax": pax
        },
        "scan_status": scraping_results["status"],
        "booking_options": booking_options
    }
