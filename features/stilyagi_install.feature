Feature: Configure Vale to use the latest Concordat release
  Scenario: Install the latest package into .vale.ini
    Given a working directory with a Vale config file
    And a fake GitHub API reporting version 9.9.9
    When I run stilyagi install for leynos/concordat-vale against that API
    Then the Vale config lists the Concordat package URL and settings
