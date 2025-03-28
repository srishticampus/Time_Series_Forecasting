from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
import re
from .models import User
from django.contrib.auth.hashers import make_password
from django.contrib.auth import authenticate,login,logout
from django.urls import reverse




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


def dashboard(request):
    user = User.objects.all()
    return render(request,'dashboard.html',{'user': user})