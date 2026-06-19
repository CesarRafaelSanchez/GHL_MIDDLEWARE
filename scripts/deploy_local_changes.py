import os
import paramiko

def deploy():
    host = "100.112.88.76"
    port = 22
    username = "soporte_futura_main"
    password = "Futura2026!"
    
    local_dir = r"c:\Users\cesar\PycharmProjects\GHL_System"
    remote_dir = "/home/soporte_futura_main/GHL_System"
    
    files_to_deploy = [
        "app/__init__.py",
        "app/routes/webhooks.py",
        "scripts/reconcile_ghl_tags.py"
    ]
    
    print(f"Connecting to {host} via SSH...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port, username, password)
    
    print("Opening SFTP channel...")
    sftp = ssh.open_sftp()
    
    for file_path in files_to_deploy:
        local_path = os.path.join(local_dir, file_path.replace('/', '\\'))
        remote_path = f"{remote_dir}/{file_path}"
        print(f"Uploading {local_path} -> {remote_path} ...")
        sftp.put(local_path, remote_path)
    
    sftp.close()
    print("SFTP Upload completed.")
    
    # Rebuild docker container if needed
    cmd = f"cd {remote_dir} && docker compose down && docker compose up -d --build"
    print(f"Running remote command: {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    exit_status = stdout.channel.recv_exit_status()
    print("Command Output:")
    print(stdout.read().decode())
    print("Command Error:")
    print(stderr.read().decode())
    
    # Run dry-run reconciliation remotely using the host's virtualenv python
    cmd_dryrun = f"cd {remote_dir} && export PYTHONIOENCODING=utf-8 && .venv/bin/python scripts/reconcile_ghl_tags.py --dry-run"
    print(f"Running remote dry-run: {cmd_dryrun}")
    stdin, stdout, stderr = ssh.exec_command(cmd_dryrun)
    exit_status_dryrun = stdout.channel.recv_exit_status()
    print("Dry-Run Output:")
    print(stdout.read().decode())
    print("Dry-Run Error:")
    print(stderr.read().decode())
    
    print(f"Deployment finished with exit status: {exit_status}")
    ssh.close()

if __name__ == "__main__":
    deploy()
