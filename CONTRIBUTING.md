# Contributing to Imager-Service

Thank you for considering contributing to the Imager-Service! This guide will help you set up the environment and get started with development.

## Setting Up the Development Environment

The Imager-Service consists of three main components: Manager (UI), Scheduler (API), and MongoDB. Follow these steps to run them locally:

* Fork the repo - https://github.com/offspot/imager-service

```bash
# Clone the repository
git clone https://github.com/<your-username>/imager-service.git
cd imager-service

# Create required data directories
mkdir -p data/{media,static,mongo}

# Build and start all services
docker-compose build
docker-compose up -d

# Check if all services are running
docker-compose ps
```

After running these commands, you can access:
- Manager UI at http://localhost:8000 

## Default Admin Access

The system automatically creates an admin user on first run with these credentials:
```
Username: admin
Password: admin
```

You can use these credentials to log in at http://localhost:8000/login/

## Development Workflow

1. Make changes to the code
2. To see your changes reflected:

```bash
docker-compose down
docker-compose build
docker-compose up -d
# To view logs
docker-compose logs -f manager
```

## Common Development Tasks

### Accessing Container Shells
```bash
# Manager container
docker-compose exec manager bash

# Scheduler container
docker-compose exec scheduler bash

# MongoDB container
docker-compose exec mongo mongo
```

### Database Operations
```bash
# Make and apply migrations
docker-compose exec manager bash
source manager-env/bin/activate
python manage.py makemigrations
python manage.py migrate

# Reset database
docker-compose down -v
docker-compose up -d
```

### Rebuilding Services
```bash
# Rebuild specific service
docker-compose build manager #If you want to rebuild scheduler, replace manager with scheduler

# Rebuild all services
docker-compose build

# Rebuild and restart everything
docker-compose down
docker-compose build
docker-compose up -d
```

## Now you can start contributing
### Quick guide for Manager

The Manager is the web interface component written in Django. Here's how to work with it:

1. **Project Structure**
```
manager/
├── manager/          # Main Django app
│   ├── models.py     # Database models
│   ├── views/        # View logic
│   ├── templates/    # HTML templates
|   ...
│   └── migrations/   # Database migrations
├── tests/            # Test files
└── manage.py         # Django management script
```

2. **Making Changes**

- **Templates**: Edit files in `manager/templates/` to modify the UI
- **Backend Logic**: Edit files in `manager/views/` to modify API endpoints and page handlers
- **Database Changes**: 
  ```bash
  # After modifying models.py
  docker-compose exec manager bash
  source manager-env/bin/activate
  python manage.py makemigrations
  python manage.py migrate
  ```

3. **Best Practices**
- Use `black` for code formatting.
- Run `ruff` for linting.
- Add meaningful docstrings to public functions and classes

## Troubleshooting

If you encounter issues:
1. Check logs: `docker-compose logs -f`
2. Ensure all containers are running: `docker-compose ps`
3. Try rebuilding: `docker-compose down && docker-compose up -d --build`
4. Clear volumes: `docker-compose down -v`

Happy coding!