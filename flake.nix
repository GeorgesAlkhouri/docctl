{
  description = "Description for the project";

  inputs = {
    noospherix.url = "github:GeorgesAlkhouri/noospherix";
    nixpkgs.follows = "noospherix/nixpkgs";
    nixpkgs-unstable.follows = "noospherix/nixpkgs-unstable";
    flake-parts.follows = "noospherix/flake-parts";
  };

  nixConfig = {
    extra-trusted-public-keys = "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw=";
    extra-substituters = "https://devenv.cachix.org";
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [ inputs.noospherix.hub.devenv.flakeModule ];
      systems = [
        "x86_64-linux"
        "i686-linux"
        "x86_64-darwin"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      perSystem =
        {
          config,
          self',
          inputs',
          pkgs,
          system,
          ...
        }:
        let

          unstable = import inputs.noospherix.hub.nixpkgs-unstable { inherit system; };
          python' = unstable.python312.withPackages (ps: with ps; [ pip-tools ]);
        in
        {
          devenv.shells.default = {
            name = "docctl";

            env = {
              OPENCODE_ENABLE_EXA = "1";
              UV_PYTHON_PREFERENCE = "only-system";
            };

            enterShell = ''
              if [ -n "$VIRTUAL_ENV" ]; then
                export UV_PYTHON="$VIRTUAL_ENV/bin/python"
              fi
            '';

            packages = with unstable; [
              git
              curl
              jq
              lychee
              gh
            ];
            languages.python = {

              enable = true;
              package = python';
              venv.enable = true;
              uv.enable = true;
            };

          };

        };
    };
}
