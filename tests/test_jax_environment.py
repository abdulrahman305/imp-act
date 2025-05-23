import time

try:
    import jax
    import jax.numpy as jnp
except ImportError:
    jax = None
    jnp = None

import numpy as np

import pytest

from imp_act.environments.jax_environment import EnvState

environment_fixtures_jax = [
    "toy_environment_2_jax",
    "cologne_environment_jax",
]


def do_nothing_policy_jax(jax_env):
    return jnp.zeros(jax_env.total_num_segments, dtype=jnp.int32)


@pytest.mark.skipif(jax is None, reason="JAX is not installed.")
@pytest.mark.parametrize("parameter_fixture", environment_fixtures_jax, indirect=True)
def test_n_episodes_jax(parameter_fixture):
    """Test if environment can run multiple episodes."""
    n_episodes = 5

    env = parameter_fixture
    action_jax = do_nothing_policy_jax(env)
    jax_for_loop_timings = []

    start_time = time.time()
    key_seed = time.time_ns()
    key = jax.random.PRNGKey(key_seed)
    print(f"\nRunning {n_episodes} episodes")
    print(f"Random seed: {key_seed}")

    # reset
    key, subkey = jax.random.split(key)
    obs, state = env.reset(subkey)
    forced_repairs_list = []

    for _ in range(n_episodes):
        done = False
        total_reward = 0
        timestep = 0
        forced_repairs = 0

        while not done:
            key, step_key = jax.random.split(key)
            obs, state, reward, done, info = env.step(step_key, state, action_jax)
            total_reward += reward
            timestep += 1
            assert done or timestep == state.timestep
            assert timestep <= env.max_timesteps
            forced_repairs += info["forced_replace_constraint_applied"]

        forced_repairs_list.append(forced_repairs)
        jax_for_loop_timings.append(start_time - time.time())

    average_time = sum(jax_for_loop_timings) / len(jax_for_loop_timings)
    print(
        f"Nodes: {env.num_nodes}, Edges: {env.num_edges}, Timesteps: {env.max_timesteps}, Trips: {env.trips.shape[0]}"
    )
    print(f"Average episode time taken: {average_time:.2} seconds")
    print(
        f"Average forced repairs: {sum(forced_repairs_list) / len(forced_repairs_list)}"
    )
    print("Test Result: ", end="")


@pytest.mark.skipif(jax is None, reason="JAX is not installed.")
def test_total_base_travel_time_toy(toy_environment_2, toy_environment_2_jax):
    """Test if total base travel time is the same for jax and numpy env"""
    assert jnp.allclose(
        toy_environment_2.base_total_travel_time,
        toy_environment_2_jax.base_total_travel_time,
        rtol=1e-2,
    )


@pytest.mark.skipif(jax is None, reason="JAX is not installed.")
def test_trips_initialization(cologne_environment, cologne_environment_jax):
    """Test trips initialization."""

    jax_env = cologne_environment_jax
    numpy_env = cologne_environment

    for source, target, num_cars in numpy_env.trips:
        assert jax_env.trips[source, target] == num_cars


@pytest.mark.skipif(jax is None, reason="JAX is not installed.")
def test_budget_action_costs_jax(
    toy_environment_2_unconstrained, toy_environment_2_unconstrained_jax
):
    """Test if budget costs match between JAX and NumPy implementations."""
    numpy_env = toy_environment_2_unconstrained
    jax_env = toy_environment_2_unconstrained_jax

    # Get random key
    key_seed = time.time_ns()
    key = jax.random.PRNGKey(key_seed)
    print(f"Random seed: {key_seed}")

    # Test each action type
    actions = [
        0,
        1,
        2,
        3,
        4,
    ]  # do-nothing, inspect, minor-repair, major-repair, replace

    for action in actions:
        # Create same action for both envs
        numpy_action = [
            [action] * len(e.segments) for e in numpy_env.graph.es["road_edge"]
        ]
        jax_action = jnp.full(jax_env.total_num_segments, action, dtype=jnp.int32)

        # Step both environments
        numpy_obs = numpy_env.reset()
        key, step_key = jax.random.split(key)
        jax_obs, jax_state = jax_env.reset(step_key)

        numpy_initial_budget = numpy_env.current_budget

        numpy_obs, numpy_reward, numpy_done, numpy_info = numpy_env.step(numpy_action)

        numpy_budget_spent = numpy_initial_budget - numpy_env.current_budget

        jax_state = jax_state.replace(
            budget_remaining=numpy_budget_spent
            * jax_env.get_budget_remaining_time(jax_state.timestep)
        )

        jax_initial_budget = jax_state.budget_remaining

        key, step_key = jax.random.split(key)
        jax_obs, jax_state, jax_reward, jax_done, jax_info = jax_env.step(
            step_key, jax_state, jax_action
        )

        jax_budget_spent = jax_initial_budget - jax_state.budget_remaining

        print(f"\nAction {action}:")
        print(f"NumPy budget spent: {numpy_budget_spent}")
        print(f"JAX budget spent: {jax_budget_spent}")

        assert (
            numpy_info["budget_constraints_applied"]
            == jax_info["budget_constraints_applied"]
        ), f"Budget constraint mismatch for action {action}"

        assert not numpy_info[
            "budget_constraints_applied"
        ], "Budget constraint has been applied"

        # Check budgets match
        assert jnp.allclose(
            numpy_budget_spent, jax_budget_spent, rtol=1e-5
        ), f"Budget mismatch for action {action}"

        # Check no negative budgets
        assert numpy_env.current_budget >= 0, "NumPy budget went negative"
        assert jax_state.budget_remaining >= 0, "JAX budget went negative"


@pytest.mark.skipif(jax is None, reason="JAX is not installed.")
def test_budget_constraints_consistency_jax(toy_environment_2, toy_environment_2_jax):
    """Test if budget constraints are applied consistently between JAX and NumPy implementations."""
    numpy_env = toy_environment_2
    jax_env = toy_environment_2_jax

    # Get random key
    key_seed = time.time_ns()
    key = jax.random.PRNGKey(key_seed)
    numpy_env.seed(
        key_seed
    )  # for reproducibility note that this does not give the same results as jax.random.PRNGKey
    print(f"\nRandom seed: {key_seed}")

    # Run multiple episodes with random actions
    n_episodes = 5

    for episode in range(n_episodes):
        # Reset both environments
        numpy_obs = numpy_env.reset()
        key, step_key = jax.random.split(key)
        jax_obs, jax_state = jax_env.reset(step_key)

        done = False
        trajectories_diverged = False

        while not done:
            # Generate random actions (same for both envs)
            key, action_key = jax.random.split(key)
            # Sample actions using numpy with specified weights
            action_weights = [0.8, 0.1, 0.05, 0.05, 0]
            actions = np.random.choice(
                5, size=jax_env.total_num_segments, p=action_weights
            ).astype(np.int32)
            jax_action = jnp.array(actions)
            numpy_action = [
                list(
                    jax_action[
                        jax_env.idxs_map[i, :][
                            jax_env.idxs_map[i, :] < jax_env.total_num_segments
                        ]
                    ]
                )
                for i in range(jax_env.num_edges)
            ]

            # Store initial budgets
            numpy_initial_budget = numpy_env.current_budget
            jax_initial_budget = jax_state.budget_remaining

            # Store initial time until renewal
            numpy_initial_time_until_renewal = numpy_obs["budget_time_until_renewal"]
            jax_initial_time_until_renewal = jax_env.get_budget_remaining_time(
                jax_state.timestep
            )

            assert (
                numpy_initial_time_until_renewal == jax_initial_time_until_renewal
            ), "Time until renewal mismatch"

            # Step both environments
            key, step_key = jax.random.split(key)
            numpy_obs, numpy_reward, numpy_done, numpy_info = numpy_env.step(
                numpy_action
            )
            jax_obs, jax_state, jax_reward, jax_done, jax_info = jax_env.step(
                step_key, jax_state, jax_action
            )

            print(f"\nEpisode {episode}, timestep {jax_state.timestep}")
            # Check if either forced repair was applied
            forced_repairs_applied = (
                numpy_info["forced_replace_constraint_applied"]
                or jax_info["forced_replace_constraint_applied"] > 0
            )
            print(
                f"Forced repairs applied - NumPy: {numpy_info['forced_replace_constraint_applied']}, JAX: {jax_info['forced_replace_constraint_applied']}"
            )

            # Compare budget changes
            numpy_budget_spent = numpy_initial_budget - numpy_env.current_budget
            jax_budget_spent = jax_initial_budget - jax_state.budget_remaining

            # Compare time until renewal
            numpy_time_until_renewal = numpy_obs["budget_time_until_renewal"]
            jax_time_until_renewal = jax_env.get_budget_remaining_time(
                jax_state.timestep
            )
            print(
                f"Time until renewal - NumPy: {numpy_time_until_renewal}, JAX: {jax_time_until_renewal}"
            )

            assert (
                numpy_time_until_renewal == jax_time_until_renewal
            ), "Time until renewal mismatch"

            # Check if budget was renewed
            numpy_budget_renewed = (
                numpy_time_until_renewal > numpy_initial_time_until_renewal
            )
            jax_budget_renewed = jax_time_until_renewal > jax_initial_time_until_renewal

            assert numpy_budget_renewed == jax_budget_renewed, "Budget renewal mismatch"

            trajectories_diverged = (
                trajectories_diverged or forced_repairs_applied
            )  # If forced repairs applied, paths diverged

            print(f"Trajectories diverged: {trajectories_diverged}")

            if not trajectories_diverged:
                print("Budget spent:")
                print(f"NumPy: {numpy_budget_spent}")
                print(f"JAX: {jax_budget_spent}")
                print(
                    f"Budget constraints applied - NumPy: {numpy_info['budget_constraints_applied']}, JAX: {jax_info['budget_constraints_applied']}"
                )

                # Check budget constraints were applied consistently
                assert (
                    numpy_info["budget_constraints_applied"]
                    == jax_info["budget_constraints_applied"]
                ), "Budget constraint application mismatch"

                trajectories_diverged = numpy_info["budget_constraints_applied"]

                # If constraints weren't applied, budgets should match exactly
                if not trajectories_diverged and not numpy_budget_renewed:
                    assert jnp.allclose(
                        numpy_budget_spent, jax_budget_spent, rtol=1e-5
                    ), "Budget change mismatch when no constraints applied"

            # Check no negative budgets
            assert numpy_env.current_budget >= 0, "NumPy budget went negative"
            assert jax_state.budget_remaining >= 0, "JAX budget went negative"

            if numpy_budget_renewed:
                trajectories_diverged = (
                    False  # If budget renewed, budget divergence is reset
                )
            done = numpy_done


@pytest.mark.skipif(jax is None, reason="JAX is not installed.")
def test_forced_repair_trigger_jax(toy_environment_2_jax):
    """Test if forced repairs are triggered correctly in JAX environment."""
    env = toy_environment_2_jax
    key = jax.random.PRNGKey(42)

    # Reset environment
    obs, state = env.reset(key)

    # Set up conditions for forced repair
    # Set worst observation and counter for first segment
    state = state.replace(
        observation=state.observation.at[0].set(
            env.num_observations - 1
        ),  # Worst state
        worst_obs_counter=state.worst_obs_counter.at[0].set(
            env.forced_replace_worst_observation_count + 1
        ),  # Above threshold
    )

    # Try to do nothing
    action = jnp.zeros(env.total_num_segments, dtype=jnp.int32)

    # Step environment
    key, step_key = jax.random.split(key)
    obs, next_state, reward, done, info = env.step(step_key, state, action)

    print("\nForced Repair Test:")
    print(f"Original action: {action[0]}")
    print(f"Applied action: {info['applied_actions'][0]}")
    print(f"Forced repair flag: {info['forced_replace_constraint_applied']}")

    # Check if forced repair was applied
    assert (
        info["forced_replace_constraint_applied"] > 0
    ), "Forced repair was not triggered"
    assert info["applied_actions"][0] == 4, "Action was not changed to replacement (4)"

    # Check if other segments were not affected
    assert jnp.all(
        info["applied_actions"][1:] == action[1:]
    ), "Other segments were incorrectly modified"


@pytest.mark.skipif(jax is None, reason="JAX is not installed.")
def test_mean_rewards_jax(toy_environment_2, toy_environment_2_jax):
    """Test if mean rewards match between JAX and NumPy implementations within tolerance."""
    numpy_env = toy_environment_2
    jax_env = toy_environment_2_jax

    n_episodes = 100  # More episodes for better statistics

    numpy_rewards = []
    jax_rewards = []
    reward_components = ["travel_time_reward", "maintenance_reward", "terminal_reward"]
    numpy_reward_components = {component: [] for component in reward_components}
    jax_reward_components = {component: [] for component in reward_components}

    # Get random key
    key_seed = time.time_ns()
    key = jax.random.PRNGKey(key_seed)
    numpy_env.seed(key_seed)
    print(f"\nRandom seed: {key_seed}")

    for episode in range(n_episodes):
        # Reset both environments
        numpy_obs = numpy_env.reset()
        key, reset_key = jax.random.split(key)
        jax_obs, jax_state = jax_env.reset(reset_key)

        numpy_episode_reward = 0
        jax_episode_reward = 0
        episode_components_numpy = {k: 0 for k in reward_components}
        episode_components_jax = {k: 0 for k in reward_components}

        done = False
        while not done:
            # Generate same random actions for both
            key, action_key = jax.random.split(key)
            jax_action = jnp.zeros(jax_env.total_num_segments, dtype=jnp.int32)
            numpy_action = [
                list(
                    jax_action[
                        jax_env.idxs_map[i, :][
                            jax_env.idxs_map[i, :] < jax_env.total_num_segments
                        ]
                    ]
                )
                for i in range(jax_env.num_edges)
            ]

            # Step both environments
            key, step_key = jax.random.split(key)
            numpy_obs, numpy_reward, numpy_done, numpy_info = numpy_env.step(
                numpy_action
            )
            jax_obs, jax_state, jax_reward, jax_done, jax_info = jax_env.step(
                step_key, jax_state, jax_action
            )

            # Accumulate rewards
            numpy_episode_reward += numpy_reward
            jax_episode_reward += jax_reward

            # Accumulate reward components
            for k in episode_components_numpy.keys():
                episode_components_numpy[k] += numpy_info["reward_elements"][k]
                episode_components_jax[k] += jax_info["reward_elements"][k]

            done = numpy_done

        numpy_rewards.append(numpy_episode_reward)
        jax_rewards.append(jax_episode_reward)

        # Store episode reward components
        for k in numpy_reward_components.keys():
            numpy_reward_components[k].append(episode_components_numpy[k])
            jax_reward_components[k].append(episode_components_jax[k])

    # Convert to numpy arrays for statistics
    numpy_rewards = np.array(numpy_rewards)
    jax_rewards = np.array(jax_rewards)

    # Calculate standard errors and tolerances
    numpy_se = numpy_rewards.std() / np.sqrt(n_episodes)
    jax_se = jax_rewards.std() / np.sqrt(n_episodes)
    rtol = 1.96 * np.sqrt(numpy_se**2 + jax_se**2) / abs(numpy_rewards.mean())

    # Print overall statistics
    print("\nOverall Reward Statistics:")
    print(f"NumPy - Mean: {numpy_rewards.mean():.2f}, SE: {numpy_se:.2f}")
    print(f"JAX   - Mean: {jax_rewards.mean():.2f}, SE: {jax_se:.2f}")
    rel_diff = abs(numpy_rewards.mean() - jax_rewards.mean()) / abs(
        numpy_rewards.mean()
    )
    print(f"Relative Difference: {rel_diff:.2%}")
    print(f"Allowed Relative Difference: {rtol:.2%}")

    # Collect all errors and tolerances
    errors = []
    errors.append("\nTotal reward:")
    errors.append(f"NumPy - Mean: {numpy_rewards.mean():.2f}, SE: {numpy_se:.2f}")
    errors.append(f"JAX   - Mean: {jax_rewards.mean():.2f}, SE: {jax_se:.2f}")
    errors.append(f"Relative Difference: {rel_diff:.2%}")
    errors.append(f"Allowed Relative Difference: {rtol:.2%}")

    # Component statistics
    for k in numpy_reward_components.keys():
        numpy_vals = np.array(numpy_reward_components[k])
        jax_vals = np.array(jax_reward_components[k])

        numpy_comp_se = numpy_vals.std() / np.sqrt(n_episodes)
        jax_comp_se = jax_vals.std() / np.sqrt(n_episodes)
        comp_rtol = (
            1.96
            * np.sqrt(numpy_comp_se**2 + jax_comp_se**2)
            / abs(numpy_vals.mean())
        )

        rel_diff = abs(numpy_vals.mean() - jax_vals.mean()) / abs(numpy_vals.mean())

        errors.append(f"\n{k}:")
        errors.append(f"NumPy - Mean: {numpy_vals.mean():.2f}, SE: {numpy_comp_se:.2f}")
        errors.append(f"JAX   - Mean: {jax_vals.mean():.2f}, SE: {jax_comp_se:.2f}")
        errors.append(f"Relative Difference: {rel_diff:.2%}")
        errors.append(f"Allowed Relative Difference: {comp_rtol:.2%}")

    # Print all errors
    print("\nError Analysis:")
    print("\n".join(errors))

    print("\nRunning assertions...")

    # Now run assertions
    for k in numpy_reward_components.keys():
        numpy_vals = np.array(numpy_reward_components[k])
        jax_vals = np.array(jax_reward_components[k])

        numpy_comp_se = numpy_vals.std() / np.sqrt(n_episodes)
        jax_comp_se = jax_vals.std() / np.sqrt(n_episodes)
        comp_rtol = (
            1.96
            * np.sqrt(numpy_comp_se**2 + jax_comp_se**2)
            / abs(numpy_vals.mean())
        )

        assert np.allclose(
            numpy_vals.mean(), jax_vals.mean(), rtol=comp_rtol
        ), f"Mean {k} mismatch: NumPy={numpy_vals.mean():.2f}, JAX={jax_vals.mean():.2f}"

    assert np.allclose(
        numpy_rewards.mean(), jax_rewards.mean(), rtol=rtol
    ), f"Mean reward mismatch: NumPy={numpy_rewards.mean():.2f}, JAX={jax_rewards.mean():.2f}"


@pytest.mark.skipif(jax is None, reason="JAX is not installed.")
def test_mean_travel_times_jax(toy_environment_2, toy_environment_2_jax):
    """Test if mean travel times match between JAX and NumPy implementations within tolerance."""
    numpy_env = toy_environment_2
    jax_env = toy_environment_2_jax

    n_episodes = 100  # More episodes for better statistics

    numpy_travel_times = []
    jax_travel_times = []

    # Get random key
    key_seed = time.time_ns()
    key = jax.random.PRNGKey(key_seed)
    numpy_env.seed(key_seed)
    print(f"\nRandom seed: {key_seed}")

    for episode in range(n_episodes):
        # Reset both environments
        numpy_obs = numpy_env.reset()
        key, reset_key = jax.random.split(key)
        jax_obs, jax_state = jax_env.reset(reset_key)

        numpy_episode_tt = []
        jax_episode_tt = []

        done = False
        while not done:
            # Generate same random actions for both
            key, action_key = jax.random.split(key)
            jax_action = jnp.zeros(jax_env.total_num_segments, dtype=jnp.int32)
            numpy_action = [
                list(
                    jax_action[
                        jax_env.idxs_map[i, :][
                            jax_env.idxs_map[i, :] < jax_env.total_num_segments
                        ]
                    ]
                )
                for i in range(jax_env.num_edges)
            ]

            # Step both environments
            key, step_key = jax.random.split(key)
            numpy_obs, _, numpy_done, numpy_info = numpy_env.step(numpy_action)
            jax_obs, jax_state, _, jax_done, jax_info = jax_env.step(
                step_key, jax_state, jax_action
            )

            # Store travel times
            numpy_episode_tt.append(numpy_info["total_travel_time"])
            jax_episode_tt.append(jax_info["total_travel_time"])

            done = numpy_done

        # Store mean travel time for episode
        numpy_travel_times.append(np.mean(numpy_episode_tt))
        jax_travel_times.append(np.mean(jax_episode_tt))

    # Convert to numpy arrays for statistics
    numpy_travel_times = np.array(numpy_travel_times)
    jax_travel_times = np.array(jax_travel_times)

    # Calculate standard errors and tolerances
    numpy_se = numpy_travel_times.std() / np.sqrt(n_episodes)
    jax_se = jax_travel_times.std() / np.sqrt(n_episodes)
    rtol = 1.96 * np.sqrt(numpy_se**2 + jax_se**2) / abs(numpy_travel_times.mean())

    # Print overall statistics
    print("\nTotal Travel Time Statistics:")
    print(f"NumPy - Mean: {numpy_travel_times.mean():.2f}, SE: {numpy_se:.2f}")
    print(f"JAX   - Mean: {jax_travel_times.mean():.2f}, SE: {jax_se:.2f}")
    rel_diff = abs(numpy_travel_times.mean() - jax_travel_times.mean()) / abs(
        numpy_travel_times.mean()
    )
    print(f"Relative Difference: {rel_diff:.2%}")
    print(f"Allowed Relative Difference: {rtol:.2%}")

    # Print base travel times
    print("\nBase Travel Times:")
    print(f"NumPy: {numpy_env.base_total_travel_time:.2f}")
    print(f"JAX: {jax_env.base_total_travel_time:.2f}")
    rel_diff_base = abs(
        numpy_env.base_total_travel_time - jax_env.base_total_travel_time
    ) / abs(numpy_env.base_total_travel_time)
    print(f"Relative Difference: {rel_diff_base:.2%}")

    # Print detailed error analysis
    errors = []
    errors.append("\nTotal Travel Time:")
    errors.append(f"NumPy - Mean: {numpy_travel_times.mean():.2f}, SE: {numpy_se:.2f}")
    errors.append(f"JAX   - Mean: {jax_travel_times.mean():.2f}, SE: {jax_se:.2f}")
    errors.append(f"Relative Difference: {rel_diff:.2%}")
    errors.append(f"Allowed Relative Difference: {rtol:.2%}")

    print("\nError Analysis:")
    print("\n".join(errors))

    print("\nRunning assertions...")

    # Assert base travel times match
    assert np.allclose(
        numpy_env.base_total_travel_time, jax_env.base_total_travel_time, rtol=1e-5
    ), f"Base travel time mismatch: NumPy={numpy_env.base_total_travel_time:.2f}, JAX={jax_env.base_total_travel_time:.2f}"

    # Assert mean travel times are within tolerance
    assert np.allclose(
        numpy_travel_times.mean(), jax_travel_times.mean(), rtol=rtol
    ), f"Mean travel time mismatch: NumPy={numpy_travel_times.mean():.2f}, JAX={jax_travel_times.mean():.2f}"


def test_get_travel_time(toy_environment_2, toy_environment_2_jax):
    "Test total travel time is the same for jax and numpy env"
    actions = [
        [1 for _ in edge["road_edge"].segments] for edge in toy_environment_2.graph.es
    ]
    timestep = 0
    done = False
    total_num_segments = sum(
        [len(edge.segments) for edge in toy_environment_2.graph.es["road_edge"]]
    )

    while not done:
        timestep += 1
        obs, _, done, info = toy_environment_2.step(actions)
        action_durations = []
        for edge in toy_environment_2.graph.es:
            for segment in edge["road_edge"].segments:
                action_durations.append(segment.action_duration)
        max_action_duration = jnp.array(max(action_durations))
        worst_obs_counter = jnp.array(
            [
                [segment.worst_observation_counter for segment in edge.segments]
                for edge in toy_environment_2.graph.es["road_edge"]
            ]
        ).flatten()
        total_travel_time_np = info["total_travel_time"]
        base_travel_times = np.empty(total_num_segments)
        capacities = np.empty(total_num_segments)
        id_counter = 0
        for edge in toy_environment_2.graph.es["road_edge"]:
            for segment in edge.segments:
                base_travel_times[id_counter] = segment.base_travel_time
                capacities[id_counter] = segment.capacity
                id_counter += 1
        jax_state = EnvState(
            damage_state=jnp.array(info["edge_states"]).flatten(),
            observation=jnp.array(obs["edge_observations"]).flatten(),
            belief=jnp.array(obs["edge_beliefs"]).flatten(),
            base_travel_time=jnp.asarray(base_travel_times),
            capacity=jnp.asarray(capacities),
            worst_obs_counter=worst_obs_counter,
            deterioration_rate=jnp.array(obs["edge_deterioration_rates"]).flatten(),
            budget_remaining=toy_environment_2.current_budget,
            timestep=timestep,
        )

        # Get JAX travel time and volumes
        (
            total_travel_time_jax,
            edge_volumes_jax,
        ) = toy_environment_2_jax._get_total_travel_time_and_edge_volumes(
            jax_state,
            toy_environment_2_jax.base_edge_volumes,
            toy_environment_2_jax.traffic_assignment_max_iterations,
        )

        # Apply worst case calculation as per _get_worst_case_travel_time
        worst_case_ttt = total_travel_time_jax
        total_travel_time_jax = (
            (1 - max_action_duration) * toy_environment_2_jax.base_total_travel_time
            + max_action_duration * worst_case_ttt
        )

        print(
            f"Total Travel Time - NumPy: {total_travel_time_np:.2f}, JAX: {total_travel_time_jax:.2f}"
        )

        # If travel times don't match closely
        if not jnp.allclose(total_travel_time_np, total_travel_time_jax, rtol=1e-2):
            print(
                f"Travel times differ: NumPy={total_travel_time_np:.2f}, JAX={total_travel_time_jax:.2f}"
            )

            # Save original initial_edge_volumes
            original_initial_edge_volumes = (
                toy_environment_2.initial_edge_volumes.copy()
            )

            # Override initial_edge_volumes with JAX volumes
            toy_environment_2.initial_edge_volumes = np.array(
                [float(v) for v in edge_volumes_jax]
            )

            # Calculate travel time with JAX volumes using NumPy implementation
            np_travel_time_with_jax_volumes = toy_environment_2._get_total_travel_time(
                set_initial_volumes=True  # Use the initial volumes we just set
            )

            # Restore original initial_edge_volumes
            toy_environment_2.initial_edge_volumes = original_initial_edge_volumes

            print(
                f"NumPy travel time with JAX volumes: {np_travel_time_with_jax_volumes}"
            )

            # Also calculate JAX travel time using NumPy volumes
            numpy_volumes = np.array(
                [edge["volume"] for edge in toy_environment_2.graph.es]
            )
            jax_numpy_volumes = jnp.array(numpy_volumes)

            # Calculate edge travel times using the JAX method with NumPy volumes
            edge_travel_times = toy_environment_2_jax.compute_edge_travel_time(
                jax_state, jax_numpy_volumes
            )
            jax_travel_time_with_numpy_volumes = jnp.sum(
                edge_travel_times * jax_numpy_volumes
            )

            print(
                f"JAX travel time with NumPy volumes: {jax_travel_time_with_numpy_volumes:.2f}"
            )
            print(f"Actual NumPy travel time: {total_travel_time_np:.2f}")
            print(f"Actual JAX travel time: {total_travel_time_jax:.2f}")

        # Original assertion
        assert jnp.allclose(
            total_travel_time_np, total_travel_time_jax, rtol=1e-2
        ), f"Travel times differ: NumPy={total_travel_time_np:.2f}, JAX={total_travel_time_jax:.2f}"


def test_get_travel_time_cologne(cologne_environment, cologne_environment_jax):
    "Test total travel time is the same for jax and numpy env"
    test_get_travel_time(cologne_environment, cologne_environment_jax)
