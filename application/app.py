from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from gtts import gTTS
import os
import requests
import time
import json 
from geopy.geocoders import Nominatim

# --- Configuration and Initialization ---

# !!! IMPORTANT: Insert your actual API Keys here for real-time data !!!
# Real-time services like OGD India, ISRIC SoilGrids, and GEE require tokens/keys
API_KEYS = {
    # Open-Meteo does not require a key
    "ISRIC_SOILGRIDS_URL": "https://rest.isric.org/soilgrids/v2.0/properties/query",
    # You would typically set up a Google Earth Engine proxy service here:
    "GEE_PROXY_URL": "http://your-ndvi-service.com/api/ndvi",
    # OGD India API often requires complex token setup:
    "OGD_INDIA_API_KEY": "YOUR_OGD_INDIA_KEY" 
}

# Initialize Flask app
app = Flask(__name__)
CORS(app) # Enable CORS for frontend communication

# Database configuration (SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gramvikas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Initialize Nominatim geocoder
geolocator = Nominatim(user_agent="GramVikasApp_Kisha")

# --- Database Model (Unchanged) ---

class Farmer(db.Model):
    """Stores persistent data about the farmer for recognition and personalization."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    language = db.Column(db.String(10), default='hi')
    
    # Coordinates derived from address using Nominatim 
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)

    # For returning user logic
    last_problem_summary = db.Column(db.String(500))
    
    # Ensures a farmer with the same name and address is unique
    __table_args__ = (db.UniqueConstraint('name', 'address', name='_name_address_uc'),)

    def __repr__(self):
        return f'<Farmer {self.name} at {self.address}>'

# --- Geocoding Function (New Real-Time Service) ---

def geocode_address(address):
    """Converts a text address (village/city) into lat/lon using Nominatim."""
    try:
        location = geolocator.geocode(address, country_codes='in')
        if location:
            return location.latitude, location.longitude
        return None, None
    except Exception as e:
        print(f"Nominatim Geocoding Error: {e}")
        return None, None

# --- API Functions (REAL and STRUCTURED Implementations) ---

def get_current_weather(latitude, longitude, lang='hi'):
    """Fetches real-time weather from Open-Meteo API."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,wind_speed_10m,precipitation&forecast_days=1"
    
    try:
        response = requests.get(url)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        current = data.get('current', {})
        temp = current.get('temperature_2m', 'N/A')
        wind_speed = current.get('wind_speed_10m', 'N/A')
        rain = current.get('precipitation', 'N/A')

        if lang == 'hi':
            return f"आपके खेत ({latitude:.2f}, {longitude:.2f}) पर आज का तापमान {temp} डिग्री सेल्सियस है। हवा की गति {wind_speed} km/h है और वर्षा {rain} mm है। सिंचाई की योजना इसी के अनुसार बनाएं।"
        return f"Current temperature at your farm ({latitude:.2f}, {longitude:.2f}) is {temp}°C. Wind speed is {wind_speed} km/h, and precipitation is {rain} mm. Plan irrigation accordingly."

    except requests.exceptions.RequestException as e:
        error_msg = "मौसम की जानकारी नहीं मिल सकी। बाहरी सेवा में त्रुटि।" if lang == 'hi' else "Could not retrieve weather information. External service error."
        print(f"Weather API Error: {e}")
        return error_msg


def get_soil_data(latitude, longitude, lang='hi'):
    """Fetches real soil data structure from ISRIC SoilGrids API."""
    
    url = API_KEYS['ISRIC_SOILGRIDS_URL']
    # We want pH and Organic Carbon (ocd) at 0-5cm depth
    properties = ["ph_h2o", "ocd"] 
    depths = ["0-5cm"]
    
    # Note: ISRIC data is scaled (e.g., pH * 10). We must divide by 10.
    
    try:
        response = requests.get(
            url,
            params={
                "lon": longitude,
                "lat": latitude,
                "properties": ",".join(properties),
                "depths": ",".join(depths)
            }
        )
        response.raise_for_status()
        data = response.json()
        
        ph = 'N/A'
        ocd = 'N/A'

        for prop in data.get('properties', []):
            prop_id = prop.get('property', {}).get('id')
            
            # The value is typically in the first interval/depth and is the mean (mean is key 'M')
            mean_value = prop.get('intervals', [{}])[0].get('values', {}).get('mean', None)
            
            if prop_id == 'ph_h2o' and mean_value is not None:
                ph = round(mean_value / 10, 1)  # pH value must be divided by 10
            elif prop_id == 'ocd' and mean_value is not None:
                ocd = f"{round(mean_value / 100, 2)}%" # Organic Carbon Density is tricky to interpret, simplifying here

        if lang == 'hi':
            return f"ISRIC डेटा के अनुसार, आपकी मिट्टी का pH स्तर लगभग **{ph}** है और जैविक कार्बन (Organic Carbon) लगभग **{ocd}** है। यह जानकारी आपकी फसल के लिए बहुत महत्वपूर्ण है।"
        return f"Based on ISRIC data, your soil pH is approximately **{ph}** and Organic Carbon is approximately **{ocd}**. This information is vital for your crop."

    except requests.exceptions.RequestException as e:
        error_msg = "मिट्टी की जानकारी नहीं मिल सकी। बाहरी सेवा में त्रुटि।" if lang == 'hi' else "Could not retrieve soil data. External service error."
        print(f"SoilGrids API Error: {e}")
        return error_msg


def get_market_prices(crop_name, lang='hi'):
    """Mocks OGD Platform India API call structure (requires key and complex query)."""
    
    # OGD India API requires structured queries (state, district, crop ID, etc.)
    # For OGD, you MUST register on the Data Portal India and get a key/set up OAuth.
    # The complexity of this API makes it unsuitable for simple replacement.
    # The following is the original structured mock, awaiting your OGD implementation.
    
    prices = {"wheat": 2200, "rice": 4000, "corn": 1800}
    price = prices.get(crop_name.lower(), "unavailable")
    
    if price != "unavailable":
        if lang == 'hi':
            hindi_crop = {"wheat": "गेहूं", "rice": "धान", "corn": "मक्का"}.get(crop_name.lower(), crop_name)
            return f"बाजार में आज **{hindi_crop}** का भाव ₹{price} प्रति क्विंटल है (OGD API setup pending)."
        return f"The current market price for **{crop_name}** is ₹{price} per quintal (OGD API setup pending)."
    return "बाजार भाव नहीं मिल सका। (OGD API setup pending)" if lang == 'hi' else "Could not retrieve market price. (OGD API setup pending)"

def get_ndvi_advice(latitude, longitude, crop_name, lang='hi'):
    """Mocks Plantix Vision/Sentinel-2 NDVI data analysis structure (requires external service)."""
    
    # Real-time NDVI requires querying Google Earth Engine (GEE) or a service like Plantix.
    # This usually involves a complex proxy API (GEE_PROXY_URL) set up by you.
    # This remains a placeholder until you set up your GEE proxy service.
    url = API_KEYS["GEE_PROXY_URL"] 
    
    if lang == 'hi':
        return f"सेटेलाइट डेटा (Sentinel-2 NDVI) के अनुसार, आपकी **{crop_name}** फसल का स्वास्थ्य सामान्य है। **अगले सप्ताह नाइट्रोजन उर्वरक डालें**।"
    return f"Satellite data (Sentinel-2 NDVI) shows your **{crop_name}** crop health is normal. **Apply Nitrogen fertilizer next week**."

def translate_and_tts(text, lang_code, session_id):
    """Uses gTTS to generate and save audio."""
    
    # NOTE: In a real app, IndicTrans2 would translate the input query
    # to English before processing and translate the final response back.
    
    try:
        # Create a static directory if it doesn't exist
        os.makedirs("static/audio", exist_ok=True)
        # Use session_id to generate a unique filename
        audio_path = f"static/audio/response_{session_id}.mp3"
        
        # Determine gTTS language code (handle 'en' and 'hi')
        tts_lang = 'en' if lang_code == 'en' else 'hi' 
        
        tts = gTTS(text=text, lang=tts_lang)
        tts.save(audio_path)
        return audio_path
    except Exception as e:
        print(f"TTS Error: {e}")
        return None


# --- Conversational State Management (Unchanged) ---

# Simple in-memory storage for session state (step, farmer info)
# In a production environment, this should be stored in Redis or a dedicated session store.
session_states = {}

def get_session_data(session_id):
    """Retrieves session state, initializing if necessary."""
    if session_id not in session_states:
        session_states[session_id] = {
            'step': 0, # 0: Language Select, 1: Ask Name, 2: Ask Problem, 3: API Advice, 4+: Active Chat
            'name': None,
            'address': None,
            'lang': 'hi',
            'farmer_id': None, # ID if registered farmer
            'problem_text': None
        }
    return session_states[session_id]

# --- Flask Endpoints (Logic Updated) ---

# 1. Endpoint to initiate the session 
@app.route('/api/start_session', methods=['POST'])
def start_session():
    """Initializes session and returns the first question."""
    data = request.json
    session_id = data.get('session_id')
    lang = data.get('lang', 'hi')
    
    if not session_id:
        return jsonify({'error': 'Missing session ID'}), 400
    
    session_data = get_session_data(session_id)
    session_data['lang'] = lang
    
    # The first universal question is to get name and address to identify the farmer
    session_data['step'] = 1 
    
    if lang == 'hi':
        welcome_text = "नमस्ते! मैं आपकी कृषि सलाहकार, 'कीशा' हूँ। कृपया अपना नाम और गाँव/पता बताएं।"
    else:
        welcome_text = "Hello! I am your agricultural advisor, 'Kisha'. Please tell me your name and village/address."

    # Generate TTS audio for the welcome message
    audio_path = translate_and_tts(welcome_text, lang, session_id)

    return jsonify({
        'text_response': welcome_text,
        'audio_url': audio_path.replace('static/', '/audio/'),
        'next_step': 1 
    })


# 2. Main conversational endpoint
@app.route('/api/chat', methods=['POST'])
def handle_conversation():
    """Handles messages based on the current step and session state."""
    data = request.json
    session_id = data.get('session_id')
    farmer_input = data.get('query', '').strip()
    
    if not session_id or not farmer_input:
        return jsonify({'error': 'Missing session ID or query'}), 400
    
    session_data = get_session_data(session_id)
    step = session_data['step']
    lang = session_data['lang']
    
    # --- STEP 1: Process Name and Address Input ---
    if step == 1:
        # Simple parsing logic (can be improved with NLU)
        parts = [p.strip().title() for p in farmer_input.split(',')]
        if len(parts) < 2:
             parts = [p.strip().title() for p in farmer_input.split()]
        
        # At least attempt to capture one name part and the rest as address
        name = parts[0] if parts else 'Kisan'
        address = ' '.join(parts[1:]) if len(parts) > 1 else 'Unknown Address'
        
        session_data['name'] = name
        session_data['address'] = address
        
        # --- Returning User Recognition Logic ---
        farmer = Farmer.query.filter_by(name=name, address=address).first()
        
        if farmer:
            # RETURNING USER LOGIC
            session_data['farmer_id'] = farmer.id
            session_data['step'] = 3 # Skip step 2 (Ask Problem) if a summary is available
            
            if farmer.last_problem_summary:
                # Personalized Greeting
                if lang == 'hi':
                    response_text = f"नमस्ते, {farmer.name}! पिछली बार आपको '{farmer.last_problem_summary}' की समस्या थी। क्या वह हल हो गई है, या आप किसी नई समस्या का सामना कर रहे हैं?"
                else:
                    response_text = f"Welcome back, {farmer.name}! Last time you faced an issue with '{farmer.last_problem_summary}'. Has that been solved, or are you facing a new problem?"
            else:
                # Returning user but no previous problem data
                session_data['step'] = 2 
                if lang == 'hi':
                    response_text = f"आपका फिर से स्वागत है, {farmer.name}! कृपया अपनी मुख्य कृषि समस्या बताएं।"
                else:
                    response_text = f"Welcome back, {farmer.name}! Please tell me your main agricultural problem."
        else:
            # NEW USER LOGIC
            session_data['step'] = 2 
            if lang == 'hi':
                response_text = f"धन्यवाद {name}! अब कृपया अपनी मुख्य कृषि समस्या बताएं。"
            else:
                response_text = f"Thank you {name}! Now, please tell me your main agricultural problem."
                
        # Commit the name/address of the NEW farmer now.
        if not farmer:
             new_farmer = Farmer(name=name, address=address, language=lang)
             db.session.add(new_farmer)
             db.session.commit()
             session_data['farmer_id'] = new_farmer.id
             
        db.session.close()
        audio_path = translate_and_tts(response_text, lang, session_id)
        
        return jsonify({
            'text_response': response_text,
            'audio_url': audio_path.replace('static/', '/audio/'),
            'next_step': session_data['step']
        })

    # --- STEP 2: Process Problem Input (Leads to Geocoding and API Advice) ---
    elif step == 2:
        problem_text = farmer_input
        session_data['problem_text'] = problem_text
        session_data['step'] = 3
        
        # Update the database with the problem summary and geocode the address
        farmer = Farmer.query.get(session_data['farmer_id'])
        
        if farmer:
            farmer.last_problem_summary = problem_text
            lat, lon = geocode_address(farmer.address) # <-- REAL NOMINATIM CALL
            
            if lat and lon:
                farmer.lat = lat
                farmer.lon = lon
                db.session.commit()
                db.session.close()
                
                # Proceed to giving API-based advice
                return get_api_advice(session_id, lat, lon, problem_text, lang)
            else:
                db.session.close()
                response_text = "क्षमा करें, हम आपके पते के लिए GPS स्थान नहीं ढूंढ पाए। कृपया अपना पता थोड़ा स्पष्ट करके दें।" if lang == 'hi' else "Sorry, we could not find the GPS location for your address. Please provide a slightly clearer address."
                audio_path = translate_and_tts(response_text, lang, session_id)
                session_data['step'] = 1 # Revert to step 1 to ask for address again
                return jsonify({
                    'text_response': response_text,
                    'audio_url': audio_path.replace('static/', '/audio/'),
                    'next_step': 1
                })
        else:
            response_text = "आंतरिक त्रुटि: किसान रिकॉर्ड नहीं मिला।" if lang == 'hi' else "Internal error: Farmer record not found."
            db.session.close()
            audio_path = translate_and_tts(response_text, lang, session_id)
            return jsonify({
                'text_response': response_text,
                'audio_url': audio_path.replace('static/', '/audio/'),
                'next_step': 1
            })


    # --- STEP 3/4/5+: Active Chat (API-Driven Response) ---
    elif step >= 3:
        # Re-fetch farmer details to ensure we have lat/lon
        farmer = Farmer.query.get(session_data['farmer_id'])
        if not farmer or not farmer.lat:
            if lang == 'hi':
                return jsonify({'text_response': 'कृपया अपना पता सही से बताएं ताकि मैं आपके खेत के लिए सटीक जानकारी दे सकूं।', 'next_step': 1}), 400
            else:
                return jsonify({'text_response': 'Please provide your address so I can retrieve location-based data.', 'next_step': 1}), 400
        
        # Treat subsequent inputs as requests for specific data
        return get_active_chat_response(session_id, farmer, farmer_input, lang)
        
    return jsonify({'error': 'Invalid conversation step.'}), 400

# 3. Helper function to compile and send API-based advice
def get_api_advice(session_id, lat, lon, problem_text, lang):
    """Combines multiple real/mocked API calls into a single, detailed response."""
    
    # Simple keyword extraction for crop (for NDVI/Market Price Mocks)
    crop_name = 'rice' 
    
    # --- REAL-TIME DATA ---
    weather_info = get_current_weather(lat, lon, lang)
    soil_info = get_soil_data(lat, lon, lang)
    ndvi_advice = get_ndvi_advice(lat, lon, crop_name, lang)

    if lang == 'hi':
        # Compile a detailed response
        final_advice = f"**समस्या:** {problem_text}\n"
        final_advice += f"**मौसम की जानकारी:** {weather_info}\n"
        final_advice += f"**मिट्टी की सलाह:** {soil_info}\n"
        final_advice += f"**फसल स्वास्थ्य रिपोर्ट:** {ndvi_advice}\n\n"
        final_advice += "बाजार भाव जानने के लिए 'बाजार भाव' टाइप करें।"
    else:
        final_advice = f"**Problem:** {problem_text}\n"
        final_advice += f"**Weather Info:** {weather_info}\n"
        final_advice += f"**Soil Advice:** {soil_info}\n"
        final_advice += f"**Crop Health Report:** {ndvi_advice}\n\n"
        final_advice += "To know market prices, type 'market price'."
    
    audio_path = translate_and_tts(final_advice, lang, session_id)
    
    # Advance step to allow market price queries
    session_states[session_id]['step'] = 4 

    return jsonify({
        'text_response': final_advice,
        'audio_url': audio_path.replace('static/', '/audio/'),
        'next_step': session_states[session_id]['step']
    })


# 4. Helper function for queries once the primary advice is given (Step 4+)
def get_active_chat_response(session_id, farmer, query_text, lang):
    """Handles specific follow-up queries like 'market price' or 'weather'."""
    
    query = query_text.lower()
    response_text = ""
    
    # Mocking crop name extraction from the problem summary
    crop_name = 'wheat' 
    
    # Simple query matching
    if ('बाजार' in query or 'कीमत' in query or 'price' in query or 'market' in query) and farmer.last_problem_summary:
        response_text = get_market_prices(crop_name, lang)
    elif 'मौसम' in query or 'weather' in query or 'तापमान' in query or 'temperature' in query:
        response_text = get_current_weather(farmer.lat, farmer.lon, lang)
    elif 'मिट्टी' in query or 'soil' in query or 'ph' in query:
        response_text = get_soil_data(farmer.lat, farmer.lon, lang)
    elif 'धन्यवाद' in query or 'thanks' in query:
        response_text = "आपकी मदद करके खुशी हुई। ग्राम विकास का उपयोग करने के लिए धन्यवाद! जल्द ही फिर मिलते हैं।" if lang == 'hi' else "Happy to help you. Thank you for using Gram Vikas! See you soon."
    else:
        response_text = "मैं अभी केवल मौसम, मिट्टी या बाजार भाव की जानकारी दे सकता हूँ। कोई और सवाल?" if lang == 'hi' else "I can currently provide information on weather, soil, or market prices. Any other questions?"

    audio_path = translate_and_tts(response_text, lang, session_id)

    return jsonify({
        'text_response': response_text,
        'audio_url': audio_path.replace('static/', '/audio/'),
        'next_step': session_states[session_id]['step']
    })

# 5. Endpoint to serve the audio files (e.g., /audio/response_xyz.mp3)
@app.route('/audio/<filename>')
def serve_audio(filename):
    """Serves the generated audio files."""
    try:
        return send_file(f"static/audio/{filename}", mimetype='audio/mpeg', as_attachment=False)
    except FileNotFoundError:
        return "Audio file not found.", 404

# 6. Database and Run Setup

@app.cli.command('init-db')
def init_db_command():
    """Creates database tables."""
    db.create_all()
    print('Database initialized (gramvikas.db).')

# Create the database file and table on startup if not present
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    # Clean up old audio files on start for demo purposes
    # Ensure the directory exists before trying to list its contents
    audio_dir = 'static/audio'
    try:
        os.makedirs(audio_dir, exist_ok=True)
        for f in os.listdir(audio_dir):
            if f.endswith('.mp3'):
                os.remove(os.path.join(audio_dir, f))
    except Exception as e:
        # Catch and print any cleanup errors without stopping the app startup
        print(f"Error cleaning up audio directory: {e}")
        
    app.run(debug=True, port=5000)
