import joblib
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
from .models import Company, Prediction
import os

COMPANY_MODELS = {
    'AAPL': os.path.join('models', 'prophet_model_AAPL.pkl'),
    'FB': os.path.join('models', 'prophet_model_FB.pkl'),
    'AMD': os.path.join('models', 'prophet_model_AMD.pkl'),
    'INTC': os.path.join('models', 'prophet_model_INTC.pkl')
}

def load_model(company_symbol):
    """Load the pre-trained model for a company"""
    if company_symbol not in COMPANY_MODELS:
        raise ValueError(f"No model available for {company_symbol}")
    
    model_path = COMPANY_MODELS[company_symbol]
    return joblib.load(model_path)

def make_prediction(company_symbol, days=30, user=None):
    """Make prediction for a company for the next N days"""
    model = load_model(company_symbol)
    
    # Generate future dates
    start_date = datetime.now().date()
    future_dates = pd.date_range(
        start=start_date,
        periods=days,
        freq='D'
    )
    
    # Create dataframe for prediction
    future = pd.DataFrame({'ds': future_dates})
    
    # Make prediction
    forecast = model.predict(future)
    
    # Get the company instance
    company = Company.objects.get(symbol=company_symbol)
    
    # Save predictions to database
    predictions = []
    for i in range(len(future)):
        prediction = Prediction(
            company=company,
            user=user,
            forecast_date=future_dates[i].date(),
            predicted_price=forecast['yhat'][i],
            lower_bound=forecast['yhat_lower'][i],
            upper_bound=forecast['yhat_upper'][i]
        )
        predictions.append(prediction)
    
    Prediction.objects.bulk_create(predictions)
    
    return forecast