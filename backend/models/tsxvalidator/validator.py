import logging
import re
import subprocess
import os
import json
import uuid
import shutil
import sys
from typing import Dict, Any, List, Optional
from pathlib import Path


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tsx_validator.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TSXValidator:
    def __init__(self, base_dir: str = "./tsx_validator_env"):
        self.base_dir = Path(base_dir).resolve()
        self.npm_path = shutil.which("npm") or "npm"
        self.use_shell = sys.platform.startswith("win")
        self.tsc_path: Optional[str] = self._check_typescript()
        if not self.base_dir.is_dir():
            self.setup_environment()

    def setup_environment(self):
        logger.info(f"Настройка окружения в {self.base_dir}")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._create_package_json()
        self._create_tsconfig()
        self._install_dependencies()
        (self.base_dir / "src").mkdir(exist_ok=True)
        self.tsc_path = self._check_typescript()
        if not self.tsc_path:
            raise RuntimeError("TypeScript не установлен или не найден")

    def _create_package_json(self):
        package_json = {
            "name": "tsx-validator",
            "version": "1.0.0",
            "private": True,
            "dependencies": {
                "react": "^18.2.0",
                "react-dom": "^18.2.0",
                "@types/react": "^18.2.21",
                "@types/react-dom": "^18.2.7",
                "typescript": "^5.2.2",
                "@nlmk/ds-2.0": "2.5.3"
            },
            "devDependencies": {
                "@types/node": "^18.15.0"
            }
        }
        package_json_path = self.base_dir / "package.json"
        with open(package_json_path, "w") as f:
            json.dump(package_json, f, indent=2)
        logger.info(f"Создан файл package.json: {package_json_path}")

    def _create_tsconfig(self):
        tsconfig = {
          "compilerOptions": {
            "noEmit": True,
            "incremental": True,
            "extendedDiagnostics": True,
            "target": "es2015",
            "module": "esnext",
            "allowJs": True,
            "skipLibCheck": False,
            "esModuleInterop": True,
            "allowSyntheticDefaultImports": True,
            "strict": True,
            "forceConsistentCasingInFileNames": True,
            "noFallthroughCasesInSwitch": True,
            "moduleResolution": "node",
            "resolveJsonModule": True,
            "isolatedModules": True,
            "jsx": "react-jsx",
            "baseUrl": "./",
            "paths": {
              "@components/*": ["node_modules/@nlmk/ds-2.0/lib/dist/components/*"]
            }
          },
          "include": [
            "src/temp_*.tsx"
          ],
          "exclude": [
            "node_modules"
          ]
        }
        tsconfig_path = self.base_dir / "tsconfig.json"
        with open(tsconfig_path, "w") as f:
            json.dump(tsconfig, f, indent=2)
        logger.info(f"Создан файл tsconfig.json: {tsconfig_path}")

    def _install_dependencies(self):
        logger.info("Начало установки зависимостей")
        try:
            cmd = [self.npm_path, "install"]
            result = self._run_command(cmd)
            logger.info("Зависимости успешно установлены")
            logger.debug(f"Вывод npm install: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка при установке зависимостей: {e.stderr}")
            raise RuntimeError("Не удалось установить зависимости")

    def _check_typescript(self) -> Optional[str]:
        logger.info("Checking for TypeScript compiler")
        tsc_path = self.base_dir / "node_modules" / ".bin" / "tsc"
        if self.use_shell:
            tsc_path = tsc_path.with_suffix('.cmd')

        if tsc_path.exists():
            logger.info(f"TypeScript found at: {tsc_path}")
            return str(tsc_path)
        else:
            # Fallback to global tsc
            tsc_global = shutil.which("tsc")
            if tsc_global:
                logger.info(f"Global TypeScript found at: {tsc_global}")
                return tsc_global
            else:
                logger.error("TypeScript compiler not found")
                return None

    def _run_command(self, cmd: List[str]) -> subprocess.CompletedProcess:
        logger.info(f"Preparing env")
        env = os.environ.copy()
        env['PATH'] = f"{self.base_dir / 'node_modules' / '.bin'}{os.pathsep}{env.get('PATH', '')}"
        logger.info(f"Running command: {' '.join(cmd)}")
        return subprocess.run(
            cmd,
            shell=self.use_shell,
            cwd=str(self.base_dir),
            capture_output=True,
            text=True,
            check=False,
            env=env
        )

    def validate_tsx(self, tsx_code: str) -> Dict[str, Any]:
        logger.info("Starting TSX code validation")
        temp_file = self.base_dir / "src" / f"temp_{1}.tsx"

        try:
            with open(temp_file, "w", encoding='utf-8') as f:
                f.write(tsx_code)
            logger.info(f"Temporary file created: {temp_file}")

            if not self.tsc_path:
                raise RuntimeError("TypeScript compiler not found")

            cmd = [
                self.tsc_path,
                "--project", str(self.base_dir / "tsconfig.json")
            ]

            logger.info(f"Executing command: {' '.join(cmd)}...")
            result = self._run_command(cmd)
            logger.info(f"command executed.")

            logger.info(f"Command output: {result.stdout}")
            logger.info(f"Command errors: {result.stderr}")
            logger.info(f"Return code: {result.returncode}")

            parsed_errors = self._parse_errors(result.stderr or result.stdout)
            if not parsed_errors:
                logger.info("TSX code validation successful")
                return {"valid": True, "errors": []}
            else:
                logger.info(f"Errors found during TSX code validation: {parsed_errors}")
                return {"valid": False, "errors": parsed_errors}
        except Exception as e:
            logger.exception("Unexpected error during validation")
            return {"valid": False, "errors": [str(e)]}
        finally:
            self._clean_up(temp_file)

    def _log_file_contents(self, file_path: Path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.debug(f"Содержимое файла {file_path}:\n{content}")
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {file_path}: {str(e)}")

    def _parse_errors(self, error_output: str) -> List[Dict[str, str]]:
        logger.info("Парсинг ошибок компиляции")
        lines = error_output.split('\n')
        parsed_errors = []

        for line in lines:
            if 'error TS' in line and line.startswith('src/'):
                logger.debug(f"Обработка строки ошибки: {line}")
                error = self._parse_error_line(line)
                if error:
                    parsed_errors.append(error)
            else:
                logger.debug(f"Игнорирована строка: {line}")

        logger.info(f"Всего найдено ошибок в src: {len(parsed_errors)}")
        return parsed_errors

    def _parse_error_line(self, line: str) -> Optional[Dict[str, str]]:
        try:
            parts = line.split(': error TS', 1)
            if len(parts) == 2:
                location = parts[0]
                error_parts = parts[1].split(':', 1)
                if len(error_parts) == 2:
                    error_code = error_parts[0]
                    message = error_parts[1].strip()
                    location = re.search(r'\((\d+),(\d+)\)$', location).groups()
                    return {
                        "location": list(map(int, location)),
                        "code": f"TS{error_code}",
                        "message": message
                    }
            logger.warning(f"Неожиданный формат ошибки: {line}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при парсинге строки ошибки: {str(e)}")
            return None

    def _clean_up(self, temp_file: Path):
        pass
        try:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Временный файл удален: {temp_file}")
            else:
                logger.warning(f"Временный файл не найден для удаления: {temp_file}")
        except Exception as e:
            logger.error(f"Ошибка при удалении временного файла {temp_file}: {str(e)}")

    def check_environment(self) -> List[str]:
        """Проверка корректности настройки окружения"""
        issues = []

        if not shutil.which(self.npm_path):
            issues.append("npm не найден в системе")

        required_files = ["package.json", "tsconfig.json"]
        for file in required_files:
            if not (self.base_dir / file).exists():
                issues.append(f"Файл {file} не найден")

        if not (self.base_dir / "node_modules").exists():
            issues.append("Директория node_modules не найдена")

        if not self.tsc_path:
            issues.append("TypeScript компилятор не найден")

        return issues

