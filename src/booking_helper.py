#!/usr/bin/env python3
"""
Restaurant Booking Helper
CLI wrapper that uses resto_mcp.booking to find booking options.
"""

import argparse
import os
import sys

from resto_mcp.booking import investigate_restaurant_booking


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate restaurant booking options.")
    parser.add_argument("--restaurant", "-r", required=True, help="Restaurant name and/or location (e.g. 'Septime Paris').")
    parser.add_argument("--date", "-d", default="today", help="Reservation date (YYYY-MM-DD or 'today'/'tomorrow').")
    parser.add_argument("--time-start", "-s", default="19:00", help="Start time (HH:MM).")
    parser.add_argument("--time-end", "-e", default="21:00", help="End time (HH:MM).")
    parser.add_argument("--pax", "-p", type=int, default=2, help="Number of guests.")
    parser.add_argument("--api-key", "-k", help="Google Places API key. Alternatively sets via GOOGLE_MAPS_API_KEY environment variable.")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print("Error: No Google Places API key found.", file=sys.stderr)
        print("Provide it via --api-key / -k or the GOOGLE_MAPS_API_KEY env variable.", file=sys.stderr)
        sys.exit(1)
        
    try:
        data = investigate_restaurant_booking(
            restaurant_query=args.restaurant,
            date_str=args.date,
            time_start=args.time_start,
            time_end=args.time_end,
            pax=args.pax,
            api_key=api_key
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
        
    if "error" in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        sys.exit(1)
        
    details = data["restaurant_details"]
    params = data["search_parameters"]
    
    print("=" * 80)
    print(f"SEARCHING FOR RESTAURANT: '{args.restaurant}'")
    print("=" * 80)
    print(f"Name:        {details['name']}")
    print(f"Address:     {details['address']}")
    print(f"Phone:       {details['phone'] or 'N/A'}")
    print(f"Website:     {details['website'] or 'N/A'}")
    print(f"Reservable:  {'Yes' if details['reservable'] else 'No / Unknown'}")
    print(f"Google Maps: {details['google_maps_url'] or 'N/A'}")
    print()
    
    print("=" * 80)
    print("INVESTIGATING BOOKING METHODOLOGIES")
    print("=" * 80)
    print(f"Target Date:       {params['target_date']}")
    print(f"Target Time:       {params['time_start']} - {params['time_end']}")
    print(f"Guests (Pax):      {params['pax']}")
    print()
    
    print("Scanning website for reservation details...")
    print(f"Scan Status: {data['scan_status']}")
    print()
    
    print("-" * 80)
    print("AVAILABLE BOOKING METHODOLOGIES FOUND")
    print("-" * 80)
    
    methods_found = 0
    for opt in data["booking_options"]:
        methods_found += 1
        opt_type = opt["type"]
        opt_name = opt["name"]
        
        print(f"{methods_found}. [{opt_type.upper()}] {opt_name}")
        
        if opt_type == "zenchef":
            if "restaurant_id" in opt:
                print(f"   - Zenchef Restaurant ID: {opt['restaurant_id']}")
            print(f"   - Direct Prefilled URL:  {opt['booking_url']}")
        elif opt_type == "phone":
            print(f"   - Number: {opt['phone_number']}")
            print(f"   - Status: {opt['status']}")
            print("   - Note:   (ElevenLabs AI Voice booking agent integration planned for next phase).")
        elif opt_type == "email":
            for email in opt["emails"]:
                print(f"   - Email: {email}")
            print(f"   - Note:   {opt['note']}")
        elif opt_type == "website_page":
            for url in opt["urls"]:
                print(f"   - Page: {url}")
        elif "booking_url" in opt:
            print(f"   - Booking URL: {opt['booking_url']}")
            
        print()
        
    print("=" * 80)


if __name__ == "__main__":
    main()
