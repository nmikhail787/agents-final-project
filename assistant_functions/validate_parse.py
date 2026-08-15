import json 

####
#  parse router output
####
def parse_router_output(raw_output):
    try:
        data = json.loads(raw_output) # try loading as JSON
    except json.JSONDecodeError:
        return None, "not valid JSON" # not valid JSON
    return data, None

# check fields exist and have the right type
REQUIRED_FIELDS = {
    "max_price": (float, int, type(None)),
    "min_price": (float, int, type(None)),
    "subcategory": (str, type(None)),
    "brand": (str, type(None)),
    "safety_flags": (list,),
    "age_mentioned": (bool,),
    "raw_task": (str,),
}

def check_types(data):
    for field, allowed_types in REQUIRED_FIELDS.items():
        if field not in data:
            return f"missing field: {field}"
        if not isinstance(data[field], allowed_types):
            return f"wrong type for {field}: {type(data[field])}"
    return None  # no errors

# check that values make sense
VALID_SUBCATEGORIES = [
    "Play Vehicles", "Building Toys", "Collectible Toys", "Kids' Electronics",
    "Puppets & Puppet Theaters", "Tricycles, Scooters & Wagons",
    "Kids' Furniture", "Décor & Storage"
]

VALID_SAFETY_FLAGS = [
    "small_parts_choking_hazard", "age_inappropriate", "allergen_material",
    "battery_hazard", "sharp_edges_or_points", "strangulation_hazard"
]

def check_values(data):
    if data["subcategory"] is not None and data["subcategory"] not in VALID_SUBCATEGORIES:
        return f"invalid subcategory: {data['subcategory']}"

    bad_flags = [f for f in data["safety_flags"] if f not in VALID_SAFETY_FLAGS]
    if bad_flags:
        return f"invalid safety_flags: {bad_flags}"

    if data["min_price"] is not None and data["max_price"] is not None:
        if data["min_price"] > data["max_price"]:
            return "min_price is greater than max_price"

    return None  # no errors

# make one function 
def validate_router_output(raw_output):
    data, error = parse_router_output(raw_output)
    if error:
        return None, error

    error = check_types(data)
    if error:
        return None, error

    error = check_values(data)
    if error:
        return None, error

    return data, None  # success — data is safe to use

####
#  parse search results
####

def parse_mcp_result(raw_content):
    if not raw_content:
        return {"results": [], "degraded": False, "notes": []}
    text_block = raw_content[0]
    parsed = json.loads(text_block.text)
    return parsed

def clean_price(price_value):
    """Handles rag's float prices and web's '$24.99' string prices."""
    if price_value is None:
        return None
    if isinstance(price_value, (int, float)):
        return float(price_value)
    cleaned = str(price_value).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None