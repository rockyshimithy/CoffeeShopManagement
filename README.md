# Employee Management
This is a CRUD (Create, Read, Update, Delete) application for managing employees, developed with Python 3.6, Django, and Django Rest Framework. It uses SQLite as a database.

## Technologies Used
- **Python**: 3.6
- **Django**: 2.2.19
- **Django Rest Framework**: 3.11.2
- **SQLite**: 3.31.1

## Prerequisites
Before you begin, ensure you have the following installed:
- `pyenv` or `virtualenv` (for managing Python environments)

## Installation and Setup

### 1. Clone the repository
```bash
git clone https://github.com/rockyshimithy/EmployeeManagement.git
cd EmployeeManagement
```

### 2. Set up the Python environment and install dependencies
It is recommended to use `pyenv` or `virtualenv` to create a virtual environment.

```bash
# Example with pyenv
pyenv install 3.6.15 # or any 3.6.x version
pyenv local 3.6.15
python -m venv venv
source venv/bin/activate
```

Install the dependencies:
```bash
make requirements
make requirements_dev
```

### 3. Database Migrations
Apply database migrations:
```bash
make migrate_db
```

### 4. Create a Superuser (Optional)
To access the Django admin interface, create a superuser:
```bash
make superuser
```

### 5. Run the Development Server
```bash
make runserver
```

The application will be available at `http://127.0.0.1:8000/`.

## API Endpoints

The following endpoints are available:

### List all employees
```bash
curl -X GET http://127.0.0.1:8000/employees/
```

### Retrieve a specific employee
```bash
curl -X GET http://127.0.0.1:8000/employee/<id>/
```

### Create a new employee
```bash
curl -X POST -H "Content-Type: application/json" -d '{"name": "John Doe", "email": "john.doe@example.com", "department": "IT"}' http://127.0.0.1:8000/employees/
```

### Update an existing employee
```bash
curl -X PUT -H "Content-Type: application/json" -d '{"name": "Jane Doe", "email": "jane.doe@example.com", "department": "HR"}' http://127.0.0.1:8000/employee/<id>/
```

### Delete an employee
```bash
curl -X DELETE http://127.0.0.1:8000/employee/<id>/
```

## Running Tests
To run the unit tests:
```bash
make unit
```