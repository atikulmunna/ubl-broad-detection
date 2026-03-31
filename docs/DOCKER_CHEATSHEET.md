# Docker Compose Cheatsheet - UBL Infrastructure

## Common Commands

### Start/Stop Services

```bash
# Start all services in background
sudo docker-compose up -d

# Stop all services
sudo docker-compose down

# Restart a specific service
sudo docker-compose restart ai-server

# Rebuild and restart a service
sudo docker-compose build ai-server
sudo docker-compose up -d ai-server
```

### View Logs

```bash
# Follow logs for all services
sudo docker-compose logs -f

# Follow logs for specific service
sudo docker-compose logs -f ai-server

# View last 50 lines
sudo docker-compose logs ai-server | tail -50

# View last 20 lines from backend
sudo docker-compose logs backend | tail -20
```

### Check Status

```bash
# List running containers
sudo docker-compose ps

# Check service status
sudo docker ps -a
```

### Clean Up

```bash
# Stop and remove containers
sudo docker-compose down

# Remove containers and volumes
sudo docker-compose down -v

# Remove unused images
sudo docker image prune -a

# Full cleanup (dangerous!)
sudo docker system prune -a --volumes
```

## Service-Specific Commands

### AI Server

```bash
# Rebuild AI server after code changes
sudo docker-compose build ai-server
sudo docker-compose up -d ai-server

# View AI processing logs
sudo docker-compose logs -f ai-server | grep "Worker"
```

### Backend

```bash
# Restart backend
sudo docker-compose restart backend

# View backend errors
sudo docker-compose logs backend | grep "Error"
```

### LocalStack (AWS Simulation)

```bash
# Check LocalStack health
sudo docker-compose logs localstack | grep "Ready"

# Restart LocalStack
sudo docker-compose restart localstack
```

## Debugging

### Enter Container Shell

```bash
# Access AI server shell
sudo docker exec -it ai-server /bin/bash

# Access backend shell
sudo docker exec -it backend-api /bin/bash

# Access LocalStack shell
sudo docker exec -it localstack_aws /bin/bash
```

### Check Container Resources

```bash
# View resource usage
sudo docker stats

# View GPU usage (for ai-server)
nvidia-smi
```

### Network Issues

```bash
# List Docker networks
sudo docker network ls

# Inspect network
sudo docker network inspect simulation_ubl-simulation-network

# Check container connectivity
sudo docker exec ai-server ping localstack
```

## Image Management

```bash
# List all images
sudo docker images

# Remove specific image
sudo docker rmi simulation_ai-server:latest

# Build without cache
sudo docker-compose build --no-cache ai-server
```

## Volume Management

```bash
# List volumes
sudo docker volume ls

# Remove unused volumes
sudo docker volume prune

# Inspect volume
sudo docker volume inspect localstack-data
```

## Complete Rebuild Workflow

When you make changes to code or configuration:

```bash
# 1. Stop everything
sudo docker-compose down

# 2. Rebuild specific service
sudo docker-compose build ai-server

# 3. Start everything
sudo docker-compose up -d

# 4. Monitor logs
sudo docker-compose logs -f ai-server
```

## Testing the System

### Upload Test Images

```bash
# Change to client directory
cd simulation/client

# Run upload script with metadata
python upload_with_metadata.py

# Or run simple upload
python upload_direct.py
```

### Monitor Processing

```bash
# In one terminal: watch AI server
sudo docker-compose logs -f ai-server

# In another terminal: watch backend
sudo docker-compose logs -f backend
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs for errors
sudo docker-compose logs <service-name>

# Remove orphaned containers
sudo docker-compose down
sudo docker-compose up -d
```

### Out of Memory

```bash
# Check memory usage
sudo docker stats

# Restart with clean slate
sudo docker-compose down
sudo docker system prune
sudo docker-compose up -d
```

### GPU Not Available

```bash
# Check GPU status
nvidia-smi

# Verify NVIDIA runtime
sudo docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### Port Already in Use

```bash
# Find process using port 4566 (LocalStack)
sudo lsof -i :4566

# Find process using port 8000 (Backend)
sudo lsof -i :8000

# Kill process
sudo kill -9 <PID>
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `sudo docker-compose up -d` | Start all services |
| `sudo docker-compose down` | Stop all services |
| `sudo docker-compose logs -f <service>` | Follow service logs |
| `sudo docker-compose ps` | List running containers |
| `sudo docker-compose build <service>` | Rebuild service |
| `sudo docker-compose restart <service>` | Restart service |
| `sudo docker exec -it <container> bash` | Enter container shell |

## AWS CLI (LocalStack)

```bash
# List S3 buckets
aws --endpoint-url=http://localhost:4566 s3 ls

# List objects in bucket
aws --endpoint-url=http://localhost:4566 s3 ls s3://ubl-shop-audits/

# List SQS queues
aws --endpoint-url=http://localhost:4566 sqs list-queues

# View queue attributes
aws --endpoint-url=http://localhost:4566 sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/ubl-image-processing-queue \
  --attribute-names All
```
