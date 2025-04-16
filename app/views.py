#app/views.py
import os
import json
import joblib
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib.auth import login, authenticate, logout
import re
from django.contrib.auth.hashers import make_password
from .models import Company, Prediction, Review, User
from django.db import models
from .forms import ReviewForm
import io
import base64
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

# Helper Functions
def validate_password(password):
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one number.")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        errors.append("Password must contain at least one special character.")
    return errors

def registration(request):
    if request.method == "POST":
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirmPassword')

        # Basic validation
        if not all([username, email, password, confirm_password]):
            messages.error(request, "All fields are required!")
            return redirect('register')

        if password != confirm_password:
            messages.error(request, "Passwords do not match!")
            return redirect('register')

        password_errors = validate_password(password)
        if password_errors:
            for error in password_errors:
                messages.error(request, error)
            return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists!")
            return redirect('register')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered!")
            return redirect('register')

        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            messages.success(request, "Registration successful! Please login.")
            return redirect('login')
        except Exception as e:
            messages.error(request, f"Error creating user: {str(e)}")
            return redirect('register')

    return render(request, 'registration.html')

def user_login(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, "Both username and password are required!")
            return render(request, 'login.html')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "Login successful!")
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password!")

    return render(request, 'login.html')

def load_prophet_model(company_symbol):
    try:
        model_dir = os.path.join(settings.BASE_DIR, 'app', 'models')
        model_path = os.path.join(model_dir, f'prophet_model_{company_symbol}.pkl')
        os.makedirs(model_dir, exist_ok=True)
        return joblib.load(model_path) if os.path.exists(model_path) else None
    except Exception as e:
        print(f"Error loading model for {company_symbol}: {str(e)}")
        return None

def make_prediction(symbol, days, user):
    model = load_prophet_model(symbol)
    if not model:
        raise ValueError(f"No model found for {symbol}")
    
    future = model.make_future_dataframe(periods=days)
    forecast = model.predict(future)
    return forecast.tail(days)

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Logged out successfully!")
    return redirect('login')

# Main Application Views
@login_required
def dashboard(request):
    default_companies = [
        ('AAPL', 'Apple Inc.', 'Technology company'),
        ('AMD', 'Advanced Micro Devices', 'Semiconductor company'),
        ('FB', 'Facebook (Meta)', 'Social media company'),
        ('INTC', 'Intel Corporation', 'Semiconductor company'),
    ]
    
    for symbol, name, description in default_companies:
        Company.objects.get_or_create(symbol=symbol, defaults={'name': name, 'description': description})

    companies = Company.objects.all()
    recent_predictions = Prediction.objects.filter(user=request.user).order_by('-created_at')[:5]
    
    return render(request, 'dashboard.html', {
        'companies': companies,
        'recent_predictions': recent_predictions
    })

@never_cache
@login_required(login_url='login')
def forecast_stock(request):
    if request.method == "GET":
        companies = Company.objects.all()
        return render(request, "forecast.html", {
            'companies': companies,
            'current_date': datetime.now().date()
        })

    if request.method == "POST":
        try:
            company_symbol = request.POST.get("company")
            start_date_str = request.POST.get("start_date")
            period = int(request.POST.get("period", "30"))
            freq = request.POST.get("frequency", "D")
            
            if not company_symbol or not start_date_str:
                return JsonResponse({"error": "Company and start date are required."}, status=400)

            model = load_prophet_model(company_symbol)
            if not model:
                return JsonResponse({"error": f"Model for {company_symbol} not found."}, status=400)

            # Convert and validate start date
            try:
                start_date = pd.to_datetime(start_date_str).tz_localize(None)
            except ValueError:
                return JsonResponse({"error": "Invalid start date format. Use YYYY-MM-DD."}, status=400)

            # Get the last training date from the model
            last_training_date = pd.to_datetime(model.history['ds'].max()).tz_localize(None)
            
            # Calculate days needed to reach start_date from last training date
            days_needed = (start_date - last_training_date).days
            
            # If start_date is before last training date, use last training date as start
            if days_needed < 0:
                start_date = last_training_date
                days_needed = 0
                messages.info(request, 
                    f"Start date adjusted to model's last training date: {last_training_date.strftime('%Y-%m-%d')}"
                )

            # Generate future dataframe
            future = model.make_future_dataframe(
                periods=days_needed + period,  # Enough to cover from last training to end of period
                freq=freq,
                include_history=False
            )
            
            # Filter to only include dates from start_date onward
            future = future[future['ds'] >= start_date]
            
            # Make sure we have enough data
            if len(future) < period:
                # If not enough, generate more periods
                additional_periods = period - len(future)
                more_future = model.make_future_dataframe(
                    periods=additional_periods,
                    freq=freq,
                    include_history=False
                )
                future = pd.concat([future, more_future])
            
            # Limit to the requested period
            future = future.head(period)
            forecast = model.predict(future)
            
            # Prepare dates for JSON
            forecast_dates = forecast['ds'].dt.strftime('%Y-%m-%d').tolist()
            
            company = get_object_or_404(Company, symbol=company_symbol)

            # Save predictions
            Prediction.objects.filter(company=company, user=request.user).delete()
            for _, row in forecast.iterrows():
                Prediction.objects.create(
                    company=company,
                    user=request.user,
                    forecast_date=row['ds'].date(),
                    predicted_price=row['yhat'],
                    lower_bound=row['yhat_lower'],
                    upper_bound=row['yhat_upper']
                )

            # Generate Prophet plot
            fig, ax = plt.subplots(figsize=(10, 5))
            model.plot(forecast, ax=ax)
            ax.set_title(f"{company.name} Forecast")
            ax.set_xlabel("Date")
            ax.set_ylabel("Price ($)")

            buf = io.BytesIO()
            canvas = FigureCanvas(fig)
            canvas.print_png(buf)
            plt.close(fig)
            image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            image_url = f"data:image/png;base64,{image_base64}"

            response_data = {
                "forecast": {
                    "x": forecast_dates,
                    "y": forecast["yhat"].tolist(),
                    "upper": forecast["yhat_upper"].tolist(),
                    "lower": forecast["yhat_lower"].tolist(),
                    "weekly": forecast["weekly"].tolist(),
                    "yearly": forecast["yearly"].tolist()
                },
                "trend": {
                    "x": forecast_dates,
                    "y": forecast["trend"].tolist()
                },
                "weekly": {
                    "x": forecast_dates,
                    "y": forecast["weekly"].tolist()
                },
                "yearly": {
                    "x": forecast_dates,
                    "y": forecast["yearly"].tolist()
                },
                "company_name": company.name,
                "company_symbol": company.symbol,
                "prophet_default": image_url,
                "last_training_date": last_training_date.strftime('%Y-%m-%d')
            }

            return JsonResponse(response_data)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

@login_required
def predict_stock(request, symbol):
    company = get_object_or_404(Company, symbol=symbol)
    
    if request.method == 'POST':
        days = int(request.POST.get('days', 30))
        try:
            model = load_prophet_model(symbol)
            if not model:
                raise ValueError(f"No model found for {symbol}")
            
            # Get current date (today) and last training date
            current_date = pd.to_datetime(datetime.now().date())
            last_training_date = pd.to_datetime(model.history['ds'].max())
            
            # Calculate how many days we need to forecast from last training date
            days_needed = (current_date - last_training_date).days + days
            
            # Make sure we're not predicting the past
            if days_needed < days:
                days_needed = days  # Minimum forecast period
                messages.info(request, 
                    f"Forecast starts from model's last training date: {last_training_date.strftime('%Y-%m-%d')}"
                )
            
            # Generate future dataframe
            future = model.make_future_dataframe(periods=days_needed, include_history=False)
            
            # Filter to only include dates from current_date onward
            future = future[future['ds'] >= current_date].head(days)
            
            if future.empty:
                raise ValueError("No valid forecast dates available")
            
            forecast = model.predict(future)
            
            # Convert dates to strings
            dates = forecast['ds'].dt.strftime('%Y-%m-%d').tolist()
            
            # Generate Prophet plot
            fig, ax = plt.subplots(figsize=(10, 5))
            model.plot(forecast, ax=ax)
            ax.set_title(f"{company.name} Forecast")
            
            buf = io.BytesIO()
            canvas = FigureCanvas(fig)
            canvas.print_png(buf)
            plt.close(fig)
            image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            image_url = f"data:image/png;base64,{image_base64}"

            # Save predictions
            Prediction.objects.filter(company=company, user=request.user).delete()
            predictions = []
            for _, row in forecast.iterrows():
                pred = Prediction.objects.create(
                    company=company,
                    user=request.user,
                    forecast_date=row['ds'].date(),
                    predicted_price=row['yhat'],
                    lower_bound=row['yhat_lower'],
                    upper_bound=row['yhat_upper']
                )
                predictions.append(pred)
            
            return render(request, 'prediction_results.html', {
                'chart_data': json.dumps({
                    'dates': dates,
                    'predicted': forecast['yhat'].tolist(),
                    'upper': forecast['yhat_upper'].tolist(),
                    'lower': forecast['yhat_lower'].tolist()
                }),
                'predictions': predictions,
                'company': company,
                'days': days,
                'prophet_image': image_url,
                'forecast_start_date': current_date.strftime('%Y-%m-%d')
            })
            
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return redirect('dashboard')
    
    return redirect('dashboard')

# Review Views
@login_required
def company_reviews(request, symbol):
    company = get_object_or_404(Company, symbol=symbol)
    reviews = company.reviews.select_related('user').all()
    
    return render(request, 'company_reviews.html', {
        'company': company,
        'reviews': reviews,
        'user_review': reviews.filter(user=request.user).first(),
        'average_rating': company.reviews.aggregate(models.Avg('rating'))['rating__avg'] or 0,
    })

@login_required
def add_review(request, symbol):
    company = get_object_or_404(Company, symbol=symbol)
    
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review, created = Review.objects.update_or_create(
                company=company,
                user=request.user,
                defaults=form.cleaned_data
            )
            messages.success(request, "Review submitted!")
            return redirect('company_reviews', symbol=company.symbol)
    else:
        form = ReviewForm()
    
    return render(request, 'add_review.html', {
        'company': company,
        'form': form,
    })

@login_required
@require_POST
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    review.delete()
    messages.success(request, "Review deleted.")
    return redirect('company_reviews', symbol=review.company.symbol)