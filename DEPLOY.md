# Deploy Before You Cite

Do this in the Cloud Run console. The repo has no Dockerfile and no gcloud script. Buildpacks build the service from `pyproject.toml` and `uv.lock`. The only environment variable is `PORT`, which the entrypoint reads. Do not create an API key. Do not use Secret Manager. The runtime service account calls Vertex as itself. Give that service account the Vertex AI User role.

The service URL is https://before-you-cite-655901547612.europe-west1.run.app. `deploy_url` in `submission.json` is that URL.

## Console

1. Create a Cloud Run service from this GitHub repository (`valentinasilva8/before-you-cite`) with Developer Connect, continuous deployment, branch `main`.
2. Build with Google Cloud Buildpacks. Do not add a Dockerfile.
3. Set the container entrypoint to `uvicorn app:app --host 0.0.0.0 --port $PORT`.
4. Turn on Identity-Aware Proxy. Allow a `columbia.edu` principal. Leave unauthenticated access off.
5. Set memory to 2 GiB, request timeout to 300 seconds, and max instances to 1. Set min instances to 1 from November 9 until grading ends, so a warm instance is up and a second chat turn stays on the same process.
6. Open `/health` on the service URL. It should report 73,597 rows and commit `fb5f174f`. Push a later commit to `main` and confirm Cloud Run creates a new revision.

## Checklist

1. Developer Connect links `valentinasilva8/before-you-cite`, continuous deployment, branch `main`.
2. Source build uses Cloud Buildpacks, and the service has no Dockerfile.
3. Entrypoint is `uvicorn app:app --host 0.0.0.0 --port $PORT`.
4. Identity-Aware Proxy is on, the principal is `columbia.edu`, and unauthenticated access is off.
5. Memory is 2 GiB, timeout is 300 seconds, max instances is 1, and min instances is 1 from November 9 until grading ends.
6. `/health` shows 73,597 rows and commit `fb5f174f`, and a push to `main` creates a new revision.
