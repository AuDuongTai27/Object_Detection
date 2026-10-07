#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

class DefaultJointPublisher(Node):
    """Fallback Joint State Publisher when ros-humble-joint-state-publisher is not installed."""
    def __init__(self):
        super().__init__('dobot_default_joint_publisher')
        self.pub = self.create_publisher(JointState, 'joint_states', 10)
        self.timer = self.create_timer(0.05, self.timer_callback)
        self.joint_names = [
            'rail_joint',
            'dobot_joint_1',
            'dobot_joint_2',
            'dobot_joint_3',
            'dobot_joint_4',
            'dobot_joint_5_r'
        ]
        self.get_logger().info('DefaultJointPublisher is active. Publishing zero state for Dobot joints.')

    def timer_callback(self):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = self.joint_names
        msg.position = [0.0] * len(self.joint_names)
        self.pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = DefaultJointPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
