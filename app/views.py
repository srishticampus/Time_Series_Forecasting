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
            profile_url = reverse('dashboard')
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