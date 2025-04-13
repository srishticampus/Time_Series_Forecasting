#app/management/commands/populate_companies.py
from django.core.management.base import BaseCommand
from app.models import Company

class Command(BaseCommand):
    help = 'Populates the database with initial companies'

    def handle(self, *args, **options):
        companies = [
            {'symbol': 'AAPL', 'name': 'Apple Inc.', 'description': 'Technology company specializing in consumer electronics'},
            {'symbol': 'AMD', 'name': 'Advanced Micro Devices', 'description': 'Semiconductor company'},
            {'symbol': 'FB', 'name': 'Facebook (Meta)', 'description': 'Social media and technology company'},
            {'symbol': 'INTC', 'name': 'Intel Corporation', 'description': 'Semiconductor and technology company'},
        ]

        for company_data in companies:
            company, created = Company.objects.get_or_create(
                symbol=company_data['symbol'],
                defaults={
                    'name': company_data['name'],
                    'description': company_data['description']
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created company: {company.symbol}'))
            else:
                self.stdout.write(f'Company already exists: {company.symbol}')

        self.stdout.write(self.style.SUCCESS('Successfully populated companies'))