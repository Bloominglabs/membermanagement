# Production Hosting Recommendation

Validated on April 9, 2026.

## Recommendation

Use a single **DigitalOcean Basic Droplet** in a US region for the initial Treasurer-facing production deployment, running the provided Docker Compose stack plus the production overlay in [`infra/docker-compose.prod.yml`](/home/jpt4/constructs/blbs/membermanagement/infra/docker-compose.prod.yml).

### Why this is the best fit

- It preserves the project’s self-hosted, host-portable architecture.
- A single VM is enough for initial real-world traffic while keeping ops simple.
- DigitalOcean gives a straightforward control panel for DNS, backups, and firewall rules.
- The app already fits well into a Compose-based VM deployment: Django, Postgres, Redis, Celery worker, Celery beat, and Caddy.

## Suggested QA sizing

Use **Basic shared CPU, 2 vCPU / 4 GB RAM**.

This is an inference from the current stack shape, not a quoted provider requirement:

- Django app
- Postgres
- Redis
- Celery worker
- Celery beat
- Caddy reverse proxy

That is enough for initial production use without paying for a larger dedicated box up front. If real traffic stays light, you could likely step down to 2 GB RAM later, but 4 GB is the safer starting point.

## Estimated monthly cost

As of April 9, 2026:

- DigitalOcean’s Basic Droplets are positioned for low-traffic web servers, small databases, dev/test servers, and microservices.
- The Basic **2 vCPU / 4 GB RAM** Droplet is listed at **$24.00/month**.
- DigitalOcean backups on Basic Droplets add **20%** of the Droplet cost for weekly backups or **30%** for daily backups.
- DigitalOcean Cloud Firewalls are available at **no additional cost**.
- DigitalOcean Monitoring is a **free, opt-in service**.

Recommended initial production setup:

- 1 Basic Droplet, 2 vCPU / 4 GB RAM
- Daily backups enabled

That puts the initial baseline at **about $31.20/month** before bandwidth overages or optional extras:

- `$24.00/month` Droplet
- `+$7.20/month` daily backups

## Deployment shape

### Services

- `app`: Django via Gunicorn
- `db`: Postgres
- `redis`: Redis
- `worker`: Celery worker
- `scheduler`: Celery beat
- `caddy`: public HTTPS reverse proxy

### Public endpoints

- `https://members.example.org/admin/`
- `https://members.example.org/api/`
- `https://members.example.org/healthz`

## Rollout steps

1. Create the Droplet in a US region, Ubuntu LTS image, with backups enabled.
2. Point the production DNS name such as `members.example.org` at the Droplet.
3. Copy [`infra/prod.env.example`](/home/jpt4/constructs/blbs/membermanagement/infra/prod.env.example) to a real env file and fill in secrets.
4. Set `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` to the production hostname.
5. Create a Django superuser after first boot:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/prod.env.example exec app python manage.py createsuperuser
```

6. Start the stack:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/prod.env.example up -d --build
```

7. Verify:

- `https://members.example.org/healthz` returns `{"status":"ok"}`
- Django admin login works
- the Treasurer can access the browsable API with staff credentials

## Minimum ops checklist

- Restrict inbound traffic with a cloud firewall to `80`, `443`, and `22`.
- Enable automated backups.
- Store the env file outside the repo checkout.
- Create a separate Treasurer staff account instead of sharing the superuser.
- Use Stripe and Every.org test credentials until acceptance is complete, then swap only the env values and restart the stack.

## Sources

- DigitalOcean Droplet pricing: https://docs.digitalocean.com/products/droplets/details/pricing/
- DigitalOcean Droplet plan guidance: https://docs.digitalocean.com/products/droplets/concepts/choosing-a-plan/
- DigitalOcean backups details and pricing: https://docs.digitalocean.com/products/backups/details/
- DigitalOcean Cloud Firewalls reference: https://docs.digitalocean.com/products/networking/firewalls/reference/
- DigitalOcean DNS docs: https://docs.digitalocean.com/products/networking/dns/
- DigitalOcean monitoring overview: https://docs.digitalocean.com/products/monitoring/concepts/metrics/
