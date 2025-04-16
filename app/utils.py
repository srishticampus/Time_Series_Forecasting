#app/utils.py
import joblib
import pandas as pd
from datetime import datetime
import os
from django.conf import settings
from django.core.cache import cache
from .models import Company, Prediction

COMPANY_MODELS = {
    'AAPL': os.path.join(settings.BASE_DIR, 'models', 'prophet_model_AAPL.pkl'),
    'FB': os.path.join(settings.BASE_DIR, 'models', 'prophet_model_FB.pkl'),
    'AMD': os.path.join(settings.BASE_DIR, 'models', 'prophet_model_AMD.pkl'),
    'INTC': os.path.join(settings.BASE_DIR, 'models', 'prophet_model_INTC.pkl')
}

def validate_model(model):
    """Validate that the loaded model has required methods"""
    required_methods = ['make_future_dataframe', 'predict']
    if not all(hasattr(model, attr) for attr in required_methods):
        raise ValueError(f"Invalid model - missing required methods: {required_methods}")
    return model

def load_model(company_symbol):
    """Load the pre-trained model for a company with caching"""
    if company_symbol not in COMPANY_MODELS:
        raise ValueError(f"No model available for {company_symbol}")
    
    cache_key = f'prophet_model_{company_symbol}'
    model = cache.get(cache_key)
    
    if model is None:
        try:
            model_path = COMPANY_MODELS[company_symbol]
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model file not found at {model_path}")
            
            model = joblib.load(model_path)
            model = validate_model(model)
            cache.set(cache_key, model, timeout=3600)  # Cache for 1 hour
        except Exception as e:
            raise RuntimeError(f"Error loading model for {company_symbol}: {str(e)}")
    
    return model

def make_prediction(company_symbol, days=30, user=None):
    """
    Make prediction for a company for the next N days
    
    Args:
        company_symbol: Stock symbol (e.g., 'AAPL')
        days: Number of days to forecast (default: 30)
        user: Django User instance (optional)
    
    Returns:
        dict: {
            'company': Company instance,
            'forecast': Prophet forecast DataFrame,
            'future_dates': Generated future dates,
            'predictions': List of Prediction objects (not saved)
        }
    """
    try:
        model = load_model(company_symbol)
        company = Company.objects.get(symbol=company_symbol)
        
        # Generate future dates starting from today
        future_dates = pd.date_range(
            start=datetime.now().date(),
            periods=days,
            freq='D'
        )
        
        # Create dataframe for prediction
        future = pd.DataFrame({'ds': future_dates})
        forecast = model.predict(future)
        
        # Prepare predictions for batch create
        predictions = [
            Prediction(
                company=company,
                user=user,
                forecast_date=date.date(),
                predicted_price=row['yhat'],
                lower_bound=row['yhat_lower'],
                upper_bound=row['yhat_upper']
            )
            for date, (_, row) in zip(future_dates, forecast.iterrows())
        ]
        
        # Delete old predictions for this user/company
        Prediction.objects.filter(company=company, user=user).delete()
        
        # Bulk create new predictions
        Prediction.objects.bulk_create(predictions)
        
        return {
            'company': company,
            'forecast': forecast,
            'future_dates': future_dates,
            'predictions': predictions
        }
        
    except Company.DoesNotExist:
        raise ValueError(f"Company with symbol {company_symbol} not found")
    except Exception as e:
        raise RuntimeError(f"Prediction failed for {company_symbol}: {str(e)}")