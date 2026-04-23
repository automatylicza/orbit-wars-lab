# `web/` — vendored from Kaggle/kaggle-environments

Ten katalog zawiera JS packages wymagane przez nasz forkowany viewer
(`@kaggle-environments/core` + shared configs).

- **Źródło:** https://github.com/Kaggle/kaggle-environments
- **Commit:** `5c7de9af0be1c3840dd4dee2d8d3f80a01211f44`
- **Data pobrania:** 2026-04-21

## Reguły

1. **NIE modyfikujemy** plików w `web/core/` ani `web/config/` — to cudzy kod.
2. Przy aktualizacji (np. Kaggle wypuści visualizer update): `cp -r <repo>/web/* web/`
   potem zaktualizuj commit SHA w tym README.
3. Licencja: Apache 2.0 (dziedziczy z Kaggle/kaggle-environments).
