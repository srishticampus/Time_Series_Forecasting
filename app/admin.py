#app/admin.py
from django.contrib import admin
from .models import User, Company, Prediction
# Register your models here.

admin.site.register(User)
