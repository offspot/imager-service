# Contributing to Imager-Service Manager

Thank you for considering contributing to the Imager-Service Manager! This guide will help you set up the environment and get started with development.

## Running the Manager Locally

The Manager provides a UI for creating orders and managing users. Follow these steps to run it locally:

```bash
# Navigate to the manager directory
cd manager

# Build the Docker image
docker build -t imager-service-manager .

# Stop any running container with the same name
docker stop imager-service-manager

# Remove the container
docker rm imager-service-manager

# Run the manager on port 80
docker run -d -p 80:80 --name imager-service-manager imager-service-manager
```

After running these commands, you can access the manager UI at http://localhost:80

## Creating a Test User

To create a test user for development, follow these steps:

```bash
# Connect to the running container
docker exec -it imager-service-manager /bin/bash

# Actvate the Virtual env 
source manager-env/bin/activate

python manage.py makemigrations
python manage.py migrate

# Start a Django shell to run the Python code
python manage.py shell
```

In the Python shell, paste the following code to create a test user:

```python
# Quick user creation script
from django.utils import timezone
from datetime import timedelta
from manager.models import Organization, Profile

# Create or get organization
org, created = Organization.objects.get_or_create(
    slug="kiwix",
    defaults={
        "name": "Kiwix",
        "email": "info@kiwix.org",
        "units": 100,
        "channel": "kiwix",
        "warehouse": "kiwix",
        "public_warehouse": "download"
    }
)

# Create user with access to configurations
user = Profile.create(
    organization=org,
    first_name="testuser",
    email="user@example.com",
    username="testuser",
    password="password456",
    is_admin=True,  # Set to True to ensure full access
    expiry=timezone.now() + timedelta(days=365),
    can_order_physical=True
)

print(f"User created successfully!")
print(f"Username: testuser")
print(f"Password: password")
print(f"Organization: {org.name}")
```

After executing this code, exit the shell by typing `exit()` and then exit the container shell.

## Logging In and Getting Started

1. Open your browser and navigate to http://localhost:80
2. Login with the credentials you created:
   - Username: testuser2
   - Password: password456
3. You can now explore the UI and create orders, manage settings, etc.

## Making UI Improvements

When making changes to the UI:

1. Locate the relevant templates in the `manager/templates` directory
2. Make your changes to the HTML/CSS/JavaScript files
3. For dynamic content, refer to the Django views in `manager/views.py`
4. Rebuild the Docker image and restart the container to see your changes:

```bash
docker build -t imager-service-manager .
docker stop imager-service-manager
docker rm imager-service-manager
docker run -d -p 80:80 --name imager-service-manager imager-service-manager
```

Happy coding!