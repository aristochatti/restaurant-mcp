import pytest
from extract_list import haversine_distance, resolve_coordinates, parse_places

def test_haversine_distance():
    # Paris coordinates: 48.8566, 2.3522
    # Versailles coordinates: 48.8014, 2.1301
    # Distance is approx 17.2 km
    dist = haversine_distance(48.8566, 2.3522, 48.8014, 2.1301)
    assert 16.0 < dist < 18.0


def test_resolve_coordinates_raw():
    # Raw coordinates
    coords = resolve_coordinates("48.8566, 2.3522")
    assert coords == (48.8566, 2.3522)
    
    # Negative coordinates
    coords = resolve_coordinates("-33.8688,151.2093")
    assert coords == (-33.8688, 151.2093)


def test_parse_places_sorting_and_limiting(monkeypatch):
    # Mock geocoding to return Paris coordinates
    def mock_resolve(loc, api_key):
        return 48.8566, 2.3522
    
    monkeypatch.setattr("extract_list.resolve_coordinates", mock_resolve)

    # Raw response from Maps EntityList containing:
    # 1. Place in Versailles (approx 17 km away)
    # 2. Place in Paris (approx 1 km away)
    # 3. Place in Marseille (approx 660 km away)
    raw_response = [
        [
            ["list-123"],
            "Test List",
            "",
            ["Owner"],
            "Title",
            "Description",
            "",
            "",
            [
                # Versailles Place
                [
                    "",
                    [
                        "", "", "", "", "Versailles",
                        ["", "", 48.8014, 2.1301],
                    ],
                    "Versailles Bistro",
                ],
                # Paris Place
                [
                    "",
                    [
                        "", "", "", "", "Paris Centre",
                        ["", "", 48.8500, 2.3400],
                    ],
                    "Paris Cafe",
                ],
                # Marseille Place
                [
                    "",
                    [
                        "", "", "", "", "Marseille Port",
                        ["", "", 43.2965, 5.3698],
                    ],
                    "Marseille Seafood",
                ]
            ]
        ]
    ]

    # Test sorting by distance without limiting
    result = parse_places(raw_response, user_location="Paris, France")
    assert len(result["places"]) == 3
    # Sorted order should be: Paris Cafe (closest), Versailles Bistro (middle), Marseille Seafood (farthest)
    assert result["places"][0]["name"] == "Paris Cafe"
    assert result["places"][0]["distance_km"] < 5.0
    
    assert result["places"][1]["name"] == "Versailles Bistro"
    assert 10.0 < result["places"][1]["distance_km"] < 25.0
    
    assert result["places"][2]["name"] == "Marseille Seafood"
    assert result["places"][2]["distance_km"] > 500.0

    # Test sorting AND limiting to top 2
    result_top2 = parse_places(raw_response, user_location="Paris, France", top_n=2)
    assert len(result_top2["places"]) == 2
    assert result_top2["places"][0]["name"] == "Paris Cafe"
    assert result_top2["places"][1]["name"] == "Versailles Bistro"
