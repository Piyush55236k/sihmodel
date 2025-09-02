#!/usr/bin/env python3
"""
Crop Advisory Flask API Server
Provides ML-based crop recommendations using soil image analysis and weather data
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import logging
from datetime import datetime
import traceback
import base64
from PIL import Image
import io

# Import custom modules
from services.weather_api import WeatherService
from utils.ml_model import CropMLModel
from utils.image_processor import SoilImageProcessor

# Initialize Flask app
app = Flask(__name__)

# Configure CORS for cross-origin requests from React frontend
from flask_cors import CORS
CORS(app, origins="*", supports_credentials=True, methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize services
weather_service = WeatherService()
crop_ml_model = CropMLModel()
image_processor = SoilImageProcessor()

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_error_response(message, status_code=400, language='en'):
    """Generate standardized error response"""
    error_messages = {
        'en': message,
        'hi': message  # Add Hindi translations as needed
    }
    
    return jsonify({
        'success': False,
        'error': error_messages.get(language, message),
        'timestamp': datetime.now().isoformat(),
        'isDemoMode': True
    }), status_code

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'OK',
        'service': 'Crop Advisory API',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

@app.route('/api/crop-advisory', methods=['POST'])
def crop_advisory():
    """
    Main crop advisory endpoint
    Accepts soil image and location data, returns crop recommendations
    Handles both JSON and FormData requests
    """
    try:
        logger.info("🌾 Crop advisory request received")
        
        # Determine request type (JSON or FormData)
        if request.content_type and 'application/json' in request.content_type:
            # Handle JSON request
            data = request.get_json()
            
            # Extract location data
            location = data.get('location', {})
            latitude = location.get('latitude')
            longitude = location.get('longitude')
            
            # Extract additional info
            additional_info = data.get('additionalInfo', {})
            temperature = additional_info.get('temperature')
            rainfall = additional_info.get('rainfall')
            humidity = additional_info.get('humidity')
            weather_conditions = additional_info.get('weather_conditions')
            language = additional_info.get('language', 'en')
            
            # Handle image data (base64)
            image_data = data.get('imageData')
            if not image_data:
                return get_error_response("Soil image data is required", 400, language)
            
            # Process base64 image
            try:
                # Extract base64 data (remove data:image/...;base64, prefix)
                if 'base64,' in image_data:
                    image_base64 = image_data.split('base64,')[1]
                else:
                    image_base64 = image_data
                
                # Decode base64 image
                image_bytes = base64.b64decode(image_base64)
                image = Image.open(io.BytesIO(image_bytes))
                
                logger.info(f"📷 Image processed: {image.size} pixels, format: {image.format}")
                
            except Exception as e:
                logger.error(f"❌ Image processing error: {str(e)}")
                return get_error_response("Invalid image data format", 400, language)
                
        else:
            # Handle FormData request (legacy support)
            latitude = request.form.get('latitude')
            longitude = request.form.get('longitude')
            temperature = request.form.get('temperature')
            rainfall = request.form.get('rainfall')
            humidity = request.form.get('humidity')
            weather_conditions = request.form.get('weather_conditions')
            language = request.form.get('language', 'en')
            
            # Get uploaded image file
            if 'soil_image' not in request.files:
                return get_error_response("Soil image is required", 400, language)
            
            file = request.files['soil_image']
            if file.filename == '':
                return get_error_response("No image file selected", 400, language)
            
            if not allowed_file(file.filename):
                return get_error_response("Invalid file format. Please upload JPG, PNG, or WebP images.", 400, language)
            
            # Load image from file
            image = Image.open(file.stream)
            logger.info(f"📷 Image uploaded: {image.size} pixels, format: {image.format}")
        
        # Validate required fields
        if not latitude or not longitude:
            return get_error_response("Location coordinates are required", 400, language)
        
        # Convert coordinates to float
        try:
            lat = float(latitude)
            lon = float(longitude)
            temp = float(temperature) if temperature else None
            rain = float(rainfall) if rainfall else None
            humid = float(humidity) if humidity else None
        except ValueError:
            return get_error_response("Invalid coordinate or weather data format", 400, language)
        
        logger.info(f"📍 Location: {lat}, {lon}")
        logger.info(f"🌤️ Weather: {temp}°C, {rain}mm rain, {humid}% humidity")
        
        # Process soil image
        logger.info("🔍 Processing soil image...")
        soil_analysis = image_processor.analyze_soil_image(image)
        
        # Get additional weather data if not provided
        if not all([temp, rain, humid]):
            logger.info("🌦️ Fetching additional weather data...")
            weather_data = weather_service.get_weather_data(lat, lon)
        else:
            weather_data = {
                'temperature': temp,
                'rainfall': rain,
                'humidity': humid,
                'weather': weather_conditions
            }
        
        # Generate crop recommendations using ML model
        logger.info("🤖 Generating crop recommendations...")
        crop_recommendations = crop_ml_model.predict_crops(
            soil_analysis=soil_analysis,
            weather_data=weather_data,
            location={'latitude': lat, 'longitude': lon}
        )
        
        # Generate farming tips
        farming_tips = crop_ml_model.generate_farming_tips(
            soil_analysis=soil_analysis,
            weather_data=weather_data,
            crop_recommendations=crop_recommendations
        )
        
        # Prepare response
        response = {
            'success': True,
            'advisory_id': f"advisory_{int(datetime.now().timestamp())}",
            'timestamp': datetime.now().isoformat(),
            'location': {
                'latitude': lat,
                'longitude': lon
            },
            'soil_analysis': soil_analysis,
            'weather_data': weather_data,
            'crop_recommendations': crop_recommendations,
            'farming_tips': farming_tips,
            'confidence_score': soil_analysis.get('confidence', 0.8),
            'isDemoMode': True,
            'message': 'Crop advisory generated successfully' if language == 'en' 
                      else 'फसल सलाह सफलतापूर्वक तैयार की गई'
        }
        
        logger.info(f"✅ Crop advisory completed for location: {lat}, {lon}")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"❌ Crop advisory error: {str(e)}")
        logger.error(traceback.format_exc())
        
        return get_error_response(
            "Internal server error occurred while processing your request", 
            500, 
            language
        )

@app.route('/recommend', methods=['POST'])
def recommend():
    """
    Alias for /api/crop-advisory for compatibility with frontend
    """
    return crop_advisory()

@app.route('/api/crop-follow-up', methods=['POST'])
def crop_follow_up():
    """
    Handle follow-up questions about farming
    """
    try:
        data = request.get_json()
        question = data.get('question', '')
        advisory_context = data.get('context', {})
        language = data.get('language', 'en')
        
        if not question.strip():
            return get_error_response("Question is required", 400, language)
        
        logger.info(f"💬 Follow-up question: {question}")
        
        # Generate response using NLP/ML model
        response_data = crop_ml_model.answer_followup_question(
            question=question,
            context=advisory_context,
            language=language
        )
        
        response = {
            'success': True,
            'question': question,
            'answer': response_data,
            'confidence': 0.8,
            'timestamp': datetime.now().isoformat(),
            'isDemoMode': True
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"❌ Follow-up question error: {str(e)}")
        return get_error_response("Error processing follow-up question", 500, language)

@app.route('/api/weather/<float:lat>/<float:lon>', methods=['GET'])
def get_weather(lat, lon):
    """
    Get weather data for specific coordinates
    """
    try:
        logger.info(f"🌤️ Weather request for: {lat}, {lon}")
        
        weather_data = weather_service.get_weather_data(lat, lon)
        
        response = {
            'success': True,
            'location': {'latitude': lat, 'longitude': lon},
            'weather': weather_data,
            'timestamp': datetime.now().isoformat(),
            'isDemoMode': True
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"❌ Weather API error: {str(e)}")
        return get_error_response("Error fetching weather data", 500)

@app.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return get_error_response("File too large. Maximum size allowed is 5MB", 413)

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'timestamp': datetime.now().isoformat()
    }), 404

@app.errorhandler(500)
def internal_error(e):
    """Handle internal server errors"""
    logger.error(f"Internal server error: {str(e)}")
    return get_error_response("Internal server error", 500)

if __name__ == '__main__':
    logger.info("🚀 Starting Crop Advisory Flask API Server...")
    logger.info("📍 Available endpoints:")
    logger.info("  - POST /api/crop-advisory - Get crop recommendations")
    logger.info("  - POST /api/crop-follow-up - Ask follow-up questions")
    logger.info("  - GET /api/weather/<lat>/<lon> - Get weather data")
    logger.info("  - GET /health - Health check")
    
    # Development server
    app.run(
        host='0.0.0.0',
        port=5001,  # Different port from Node.js server
        debug=True
    )
