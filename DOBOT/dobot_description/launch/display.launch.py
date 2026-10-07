#!/usr/bin/env python3
import os
from ament_index_python.packages import get_package_share_directory, get_packages_with_prefixes
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def launch_setup(context, *args, **kwargs):
    # Locate package directory
    try:
        pkg_share = get_package_share_directory('dobot_description')
    except Exception:
        pkg_share = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    has_rail_str = LaunchConfiguration('has_rail').perform(context).lower()
    has_rail = has_rail_str in ('true', '1', 'yes')
    tool = LaunchConfiguration('tool').perform(context)

    # Select URDF based on has_rail configuration
    urdf_filename = 'dobot_magician_with_rail.urdf' if has_rail else 'dobot_magician_standalone.urdf'
    urdf_path = os.path.join(pkg_share, 'urdf', urdf_filename)

    # Fallback to local repo urdf folder if needed
    if not os.path.exists(urdf_path):
        urdf_path = os.path.join('/home/danh/FABLAB/DOBOT/dobot_description/urdf', urdf_filename)

    if not os.path.exists(urdf_path):
        raise FileNotFoundError(f"Cannot find URDF model at {urdf_path}")

    # Read URDF directly
    with open(urdf_path, 'r', encoding='utf-8') as f:
        robot_description_content = f.read()

    # RViz config file
    rviz_config_file = os.path.join(pkg_share, 'rviz', 'dobot_view.rviz')
    if not os.path.exists(rviz_config_file):
        rviz_config_file = os.path.join('/home/danh/FABLAB/DOBOT/dobot_description/rviz', 'dobot_view.rviz')

    # 1. Robot State Publisher Node
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='both',
        parameters=[{'robot_description': robot_description_content}]
    )

    # 2. Joint State Publisher (Smart Detection & Fallback)
    available_pkgs = get_packages_with_prefixes()
    nodes_to_launch = [robot_state_publisher_node]

    if 'joint_state_publisher_gui' in available_pkgs:
        nodes_to_launch.append(Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            name='joint_state_publisher_gui',
            output='screen'
        ))
    elif 'joint_state_publisher' in available_pkgs:
        nodes_to_launch.append(Node(
            package='joint_state_publisher',
            executable='joint_state_publisher',
            name='joint_state_publisher',
            output='screen'
        ))
    else:
        # Fallback to local python publisher script
        fallback_script = os.path.join(pkg_share, 'dobot_joint_state_publisher.py')
        if not os.path.exists(fallback_script):
            fallback_script = '/home/danh/FABLAB/DOBOT/dobot_description/dobot_joint_state_publisher.py'
        nodes_to_launch.append(ExecuteProcess(
            cmd=['python3', fallback_script],
            output='screen'
        ))

    # 3. RViz2 Node
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='log',
        arguments=['-d', rviz_config_file]
    )
    nodes_to_launch.append(rviz_node)

    return nodes_to_launch

def generate_launch_description():
    has_rail_arg = DeclareLaunchArgument(
        'has_rail',
        default_value='true',
        description='Whether to mount Dobot on the 1.0m Sliding Rail (true/false)'
    )
    
    tool_arg = DeclareLaunchArgument(
        'tool',
        default_value='suction_cup',
        description='End-effector tool: suction_cup, gripper, or pen'
    )

    return LaunchDescription([
        has_rail_arg,
        tool_arg,
        OpaqueFunction(function=launch_setup)
    ])
