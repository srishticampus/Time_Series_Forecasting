#app/views.py
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
import re
from .models import User, Company, Prediction
from django.contrib.auth.hashers import make_password
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .utils import make_prediction  # Import the make_prediction function
import json  # Import the json module
from django.views.decorators.cache import never_cache




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
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        confirm_password = request.POST['confirmPassword']


        if password != confirm_password:
            messages.error(request, "Passwords do not match!")
            return redirect('register')
        
        password_errors = validate_password(password)
        if password_errors:
            for error in password_errors:
                messages.error(request, error)
            return redirect('register')

        if User.objects.filter(username=username).exists() or User.objects.filter(email=email).exists():
            messages.error(request, "Student ID or Email already exists!")
            return redirect('register')
        

        user = User(
            username=username,
            email=email,
            password=make_password(password),  
        )

        user.save()

        messages.success(request, "Registration successful!")
        return redirect('login')

    return render(request,'registration.html')



def user_login(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, "Both fields are required!")
            return render(request, 'login.html')

        user = authenticate(request, username=username, password=password)
        print(user)
        if user is not None:
            login(request, user)
            messages.success(request, "Login Successful!") 
            profile_url = reverse('forecast_stock')
            return redirect(profile_url)
        else:
            messages.error(request, "Invalid Credentials!")

    return render(request, 'login.html')



@login_required
def dashboard(request):
    companies = Company.objects.all()
    
    # Get recent predictions for the user
    recent_predictions = Prediction.objects.filter(user=request.user).order_by('-created_at')[:5]
    
    context = {
        'user': request.user,
        'companies': companies,
        'recent_predictions': recent_predictions
    }
    return render(request, 'dashboard.html', context)

@login_required
def predict_stock(request, symbol):
    if request.method == 'POST':
        days = int(request.POST.get('days', 30))
        try:
            forecast = make_prediction(symbol, days, request.user)
            
            # Generate plot data for ECharts
            dates = forecast['ds'].dt.strftime('%Y-%m-%d').tolist()
            yhat = forecast['yhat'].tolist()
            yhat_upper = forecast['yhat_upper'].tolist()
            yhat_lower = forecast['yhat_lower'].tolist()
            
            chart_data = {
                'dates': dates,
                'predicted': yhat,
                'upper': yhat_upper,
                'lower': yhat_lower
            }
            
            # Get the company
            company = Company.objects.get(symbol=symbol)
            
            # Get predictions for the table
            predictions = Prediction.objects.filter(
                company=company,
                user=request.user
            ).order_by('-forecast_date')[:days]
            
            context = {
                'chart_data': json.dumps(chart_data),
                'predictions': predictions,
                'company': company,
                'days': days
            }
            
            return render(request, 'prediction_results.html', context)
            
        except Exception as e:
            messages.error(request, f"Error making prediction: {str(e)}")
            return redirect('dashboard')
    
    return redirect('dashboard')

@login_required
def admin_manage_companies(request):
    if not request.user.is_superuser:
        return redirect('dashboard')
    
    if request.method == 'POST':
        # Handle company creation/update
        pass
    
    companies = Company.objects.all()
    return render(request, 'admin/companies.html', {'companies': companies})

@login_required
def admin_view_predictions(request):
    if not request.user.is_superuser:
        return redirect('dashboard')
    
    predictions = Prediction.objects.all().order_by('-created_at')
    return render(request, 'admin/predictions.html', {'predictions': predictions})



from django.shortcuts import render
import joblib
import pandas as pd
import plotly.graph_objects as go
from django.http import JsonResponse

@login_required
def load_prophet_model(company_name):
    try:
        filename = f"app/models/prophet_model_{company_name}.pkl"
        model = joblib.load(filename)
        return model
    except Exception as e:
        return None
@never_cache
@login_required(login_url='login')
def forecast_stock(request):
    if request.method == "GET":
        return render(request, "forecast.html") 

    if request.method == "POST":
        company = request.POST.get("company")
        start_date = request.POST.get("start_date")
        period = request.POST.get("period")
        freq = request.POST.get("frequency")

        if not company or not start_date or not period:
            return JsonResponse({"error": "All fields are required."}, status=400)

        try:
            period = int(period)
        except ValueError:
            return JsonResponse({"error": "Period must be a number."}, status=400)

        model = load_prophet_model(company)
        if model is None:
            return JsonResponse({"error": f"Model for {company} not found."}, status=400)


        future_dates = model.make_future_dataframe(periods=period, freq=freq)
        forecast = model.predict(future_dates)

      # === 1. Forecast Plot with Seasonality ===
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=forecast["ds"], y=forecast["yhat"], mode="lines+markers", name="Predicted Price", line=dict(color="blue")))
        fig1.add_trace(go.Scatter(x=forecast["ds"], y=forecast["yhat_upper"], mode="lines", name="Upper Bound", line=dict(dash="dot", color="lightblue")))
        fig1.add_trace(go.Scatter(x=forecast["ds"], y=forecast["yhat_lower"], mode="lines", name="Lower Bound", line=dict(dash="dot", color="lightblue")))
        fig1.add_trace(go.Scatter(x=forecast["ds"], y=forecast["weekly"], mode="lines", name="Weekly Seasonality", line=dict(color="orange")))
        fig1.add_trace(go.Scatter(x=forecast["ds"], y=forecast["yearly"], mode="lines", name="Yearly Seasonality", line=dict(color="green")))
        fig1.update_layout(title=f"Stock Price Forecast for {company}", xaxis_title="Date", yaxis_title="Price", template="plotly_white")


        # === 2. Trend Plot ===
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=forecast["ds"], y=forecast["trend"], mode='lines', name="Trend", line=dict(color="purple")))
        fig2.update_layout(title="Trend Component", xaxis_title="Date", yaxis_title="Trend Value")

        # === 3. Weekly Seasonality Plot ===
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=forecast["ds"], y=forecast["weekly"], mode='lines', name="Weekly Seasonality", line=dict(color="orange")))
        fig3.update_layout(title="Weekly Seasonality Component", xaxis_title="Date", yaxis_title="Effect")

        # === 4. Yearly Seasonality Plot ===
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=forecast["ds"], y=forecast["yearly"], mode='lines', name="Yearly Seasonality", line=dict(color="brown")))
        fig4.update_layout(title="Yearly Seasonality Component", xaxis_title="Date", yaxis_title="Effect")

        return JsonResponse({
            "forecast": fig1.to_json(),
            "trend": fig2.to_json(),
            "weekly": fig3.to_json(),
            "yearly": fig4.to_json(),
        })


def logout_view(request):
    logout(request)
    messages.success(request, "Logged out successfully!")
    return redirect('login')