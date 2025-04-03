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
from django.contrib.auth import login, authenticate,logout
import re
from django.contrib.auth.hashers import make_password
from .models import Company, Prediction, Review, User
from django.db import models
from .forms import ReviewForm

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
            start_date = request.POST.get("start_date")
            period = int(request.POST.get("period", "30"))
            freq = request.POST.get("frequency", "D")  # Default to daily frequency
            
            if not company_symbol or not start_date:
                return JsonResponse({"error": "Company and start date are required."}, status=400)

            model = load_prophet_model(company_symbol)
            if not model:
                return JsonResponse({"error": f"Model for {company_symbol} not found."}, status=400)

            # Create future dataframe with specified frequency
            future = model.make_future_dataframe(periods=period, freq=freq)
            forecast = model.predict(future)
            company = get_object_or_404(Company, symbol=company_symbol)

            # Update or create predictions
            Prediction.objects.filter(company=company, user=request.user).delete()
            for _, row in forecast.tail(period).iterrows():
                Prediction.objects.create(
                    company=company,
                    user=request.user,
                    forecast_date=row['ds'].date(),
                    predicted_price=row['yhat'],
                    lower_bound=row['yhat_lower'],
                    upper_bound=row['yhat_upper']
                )

            # === 1. Main Forecast Plot with Seasonality ===
            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(
                x=forecast["ds"], 
                y=forecast["yhat"], 
                mode="lines+markers", 
                name="Predicted Price", 
                line=dict(color="blue")
            ))
            fig1.add_trace(go.Scatter(
                x=forecast["ds"], 
                y=forecast["yhat_upper"], 
                mode="lines", 
                name="Upper Bound", 
                line=dict(dash="dot", color="lightblue"),
                fill=None
            ))
            fig1.add_trace(go.Scatter(
                x=forecast["ds"], 
                y=forecast["yhat_lower"], 
                mode="lines", 
                name="Lower Bound", 
                line=dict(dash="dot", color="lightblue"),
                fill='tonexty',
                fillcolor='rgba(173, 216, 230, 0.2)'
            ))
            fig1.add_trace(go.Scatter(
                x=forecast["ds"], 
                y=forecast["weekly"], 
                mode="lines", 
                name="Weekly Seasonality", 
                line=dict(color="orange")
            ))
            fig1.add_trace(go.Scatter(
                x=forecast["ds"], 
                y=forecast["yearly"], 
                mode="lines", 
                name="Yearly Seasonality", 
                line=dict(color="green")
            ))
            fig1.update_layout(
                title=f"{company.name} ({company.symbol}) Price Forecast",
                xaxis_title="Date",
                yaxis_title="Price",
                template="plotly_white",
                hovermode="x unified"
            )

            # === 2. Trend Component Plot ===
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=forecast["ds"], 
                y=forecast["trend"], 
                mode='lines', 
                name="Trend", 
                line=dict(color="purple")
            ))
            fig2.update_layout(
                title="Trend Component",
                xaxis_title="Date",
                yaxis_title="Trend Value",
                template="plotly_white"
            )

            # === 3. Weekly Seasonality Plot ===
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=forecast["ds"], 
                y=forecast["weekly"], 
                mode='lines', 
                name="Weekly Seasonality", 
                line=dict(color="orange")
            ))
            fig3.update_layout(
                title="Weekly Seasonality Component",
                xaxis_title="Date",
                yaxis_title="Effect",
                template="plotly_white"
            )

            # === 4. Yearly Seasonality Plot ===
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(
                x=forecast["ds"], 
                y=forecast["yearly"], 
                mode='lines', 
                name="Yearly Seasonality", 
                line=dict(color="brown")
            ))
            fig4.update_layout(
                title="Yearly Seasonality Component",
                xaxis_title="Date",
                yaxis_title="Effect",
                template="plotly_white"
            )

            return JsonResponse({
                "forecast": fig1.to_json(),
                "trend": fig2.to_json(),
                "weekly": fig3.to_json(),
                "yearly": fig4.to_json(),
                "company_name": company.name,
                "company_symbol": company.symbol
            })

        except ValueError as e:
            return JsonResponse({"error": "Invalid input values: " + str(e)}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

@login_required
def predict_stock(request, symbol):
    company = get_object_or_404(Company, symbol=symbol)
    
    if request.method == 'POST':
        days = int(request.POST.get('days', 30))
        try:
            forecast = make_prediction(symbol, days, request.user)
            dates = forecast['ds'].dt.strftime('%Y-%m-%d').tolist()
            
            Prediction.objects.filter(company=company, user=request.user).delete()
            predictions = [
                Prediction.objects.create(
                    company=company,
                    user=request.user,
                    forecast_date=row['ds'].date(),
                    predicted_price=row['yhat'],
                    lower_bound=row['yhat_lower'],
                    upper_bound=row['yhat_upper']
                ) for _, row in forecast.iterrows()
            ]
            
            return render(request, 'prediction_results.html', {
                'chart_data': json.dumps({
                    'dates': dates,
                    'predicted': forecast['yhat'].tolist(),
                    'upper': forecast['yhat_upper'].tolist(),
                    'lower': forecast['yhat_lower'].tolist()
                }),
                'predictions': predictions,
                'company': company,
                'days': days
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